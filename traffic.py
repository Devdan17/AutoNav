#!/usr/bin/env python3
"""
Ultra-stable CARLA demo (Windows-friendly, CARLA 0.9.12)
 - ASYNC world mode (no world.tick())
 - front + third RGB cameras (moderate resolution)
 - background image saving (optional)
 - low walker counts by default
 - Traffic Manager async
 - watchdog for stream stalls
 - CLI flags: --no-save, --no-walkers, --lowres
"""

import carla
import argparse
import random
import pygame
import numpy as np
import os
import time
import logging
import threading
import queue
import csv
from collections import deque

# ---------------- Defaults / Config ----------------
OUT_DIR = "carla_dataset"
FRONT_DIR = os.path.join(OUT_DIR, "front_camera")
THIRD_DIR = os.path.join(OUT_DIR, "third_person_camera")
os.makedirs(FRONT_DIR, exist_ok=True)
os.makedirs(THIRD_DIR, exist_ok=True)

# Default resolutions (kept modest for Windows)
FRONT_W, FRONT_H = 160, 120
THIRD_W, THIRD_H = 640, 360

# Image saving frequency (frames)
CAM_SAVE_EVERY_N = 60   # save one frame every N frames (large by default)

SIM_FPS = 10            # used only for pygame clock sleeping (not server tick)

MAX_OTHER_VEHICLES = 6
MAX_CROSSERS = 2

JAYWALK_STAGING_DISTANCE = 30.0
JAYWALK_TRIGGER_DISTANCE = 12.0

NO_FRAME_TIMEOUT = 10.0   # seconds with no camera frame before watchdog triggers
MAX_TELEMETRY_ROWS = 20000

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("carla_ultrastable")

# Globals
front_image = None
third_image = None
_last_frame_time = time.time()
_frame_counter = 0

# Background image saver queue
save_queue = queue.Queue()

def image_saver(stop_event):
    """Background thread to save images to disk from the queue."""
    while not stop_event.is_set():
        try:
            path, image = save_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            # image is a carla.Image object; save_to_disk is thread-safe
            image.save_to_disk(path)
        except Exception as e:
            logger.debug("Image saver error: %s", e)
        finally:
            try:
                save_queue.task_done()
            except Exception:
                pass

def to_surface_from_image(image):
    """Convert CARLA image to pygame Surface (RGB)."""
    arr = np.frombuffer(image.raw_data, dtype=np.uint8)
    arr = arr.reshape((image.height, image.width, 4))
    arr = arr[:, :, :3][:, :, ::-1]  # BGRA -> RGB
    return pygame.surfarray.make_surface(arr.swapaxes(0, 1))

def make_camera_callback(store_name):
    """Factory to create camera callback storing a surface and queuing saves."""
    def callback(image):
        global front_image, third_image, _last_frame_time, _frame_counter
        try:
            _last_frame_time = time.time()
            _frame_counter += 1
            surf = to_surface_from_image(image)
            if store_name == "front":
                # keep small surface in memory
                front_image = surf
            else:
                third_image = surf

            # queue to save occasionally (no blocking here)
            if CAM_SAVE_EVERY_N > 0 and (image.frame % CAM_SAVE_EVERY_N == 0):
                # pick target dir
                target = FRONT_DIR if store_name == "front" else THIRD_DIR
                save_queue.put((os.path.join(target, f"{image.frame:06d}.png"), image))
        except Exception as e:
            logger.debug("camera callback error (%s): %s", store_name, e)
    return callback

def safe_is_alive(actor):
    try:
        return actor is not None and getattr(actor, "is_alive", True)
    except Exception:
        return False

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--no-save", action="store_true", help="Disable saving camera PNGs to disk")
    p.add_argument("--no-walkers", action="store_true", help="Disable spawning any walkers")
    p.add_argument("--lowres", action="store_true", help="Use lower camera resolutions")
    p.add_argument("--tm-off", action="store_true", help="Do not use Traffic Manager at all")
    p.add_argument("--quality-low", action="store_true", help="Reminder: start CarlaUE4.exe with -quality-level=Low")
    return p.parse_args()

def main():
    global CAM_SAVE_EVERY_N, FRONT_W, FRONT_H, THIRD_W, THIRD_H, _last_frame_time

    args = parse_args()
    if args.lowres:
        FRONT_W, FRONT_H = 120, 80
        THIRD_W, THIRD_H = 480, 270

    if args.no_save:
        CAM_SAVE_EVERY_N = 0

    pygame.init()
    display_w, display_h = THIRD_W, THIRD_H
    display = pygame.display.set_mode((display_w, display_h))
    pygame.display.set_caption("CARLA Ultra-Stable Demo (async mode)")

    stop_saver = threading.Event()
    saver_thread = threading.Thread(target=image_saver, args=(stop_saver,), daemon=True)
    saver_thread.start()

    # Connect to CARLA
    try:
        client = carla.Client("localhost", 2000)
        client.set_timeout(20.0)
        world = client.get_world()
    except Exception as e:
        logger.exception("Cannot connect to CARLA server: %s", e)
        stop_saver.set()
        saver_thread.join(timeout=1.0)
        return

    blueprint_library = world.get_blueprint_library()
    carla_map = world.get_map()

    # Traffic Manager (optional)
    tm = None
    if not args.tm_off:
        try:
            tm = client.get_trafficmanager(8000)
            # ensure TM runs asynchronously for stability
            try:
                tm.set_synchronous_mode(False)
            except Exception:
                pass
            tm.set_global_distance_to_leading_vehicle(2.5)
        except Exception:
            tm = None
            logger.warning("Traffic Manager unavailable or failed to initialize.")

    # Ensure server is in asynchronous mode (do not force sync)
    try:
        original_settings = world.get_settings()
        settings = world.get_settings()
        settings.synchronous_mode = False
        settings.fixed_delta_seconds = 0.0
        world.apply_settings(settings)
        logger.info("Applied asynchronous server settings.")
    except Exception as e:
        logger.warning("Failed to set server settings: %s", e)
        original_settings = None

    sensors = []
    vehicles = []
    walkers = []
    walker_controllers = []
    collisions = []
    telemetry = deque(maxlen=MAX_TELEMETRY_ROWS)

    try:
        # Spawn ego vehicle
        veh_bps = blueprint_library.filter("vehicle.tesla.model3")
        if not veh_bps:
            veh_bps = blueprint_library.filter("vehicle.*")
        if not veh_bps:
            raise RuntimeError("No vehicle blueprints available")

        spawn_point = random.choice(carla_map.get_spawn_points())
        ego = None
        for _ in range(6):
            ego = world.try_spawn_actor(random.choice(veh_bps), spawn_point)
            if ego:
                break
            spawn_point = random.choice(carla_map.get_spawn_points())

        if ego is None:
            raise RuntimeError("Failed to spawn ego vehicle")

        vehicles.append(ego)
        try:
            if tm:
                ego.set_autopilot(True, tm.get_port())
            else:
                ego.set_autopilot(True)
        except Exception:
            ego.set_autopilot(True)

        logger.info("Ego spawned (id=%s)", ego.id)

        # Collision sensor
        try:
            collision_bp = blueprint_library.find("sensor.other.collision")
            cs = world.spawn_actor(collision_bp, carla.Transform(), attach_to=ego)
            sensors.append(cs)
            def on_collision(event):
                other = event.other_actor
                msg = f"Collision with {other.type_id} at frame {event.frame}"
                logger.info(msg)
                collisions.append(msg)
            cs.listen(on_collision)
        except Exception as e:
            logger.warning("Collision sensor not available: %s", e)

        # Camera blueprints
        cam_front_bp = blueprint_library.find("sensor.camera.rgb")
        cam_front_bp.set_attribute("image_size_x", str(FRONT_W))
        cam_front_bp.set_attribute("image_size_y", str(FRONT_H))
        cam_front_bp.set_attribute("fov", "90")

        cam_third_bp = blueprint_library.find("sensor.camera.rgb")
        cam_third_bp.set_attribute("image_size_x", str(THIRD_W))
        cam_third_bp.set_attribute("image_size_y", str(THIRD_H))
        cam_third_bp.set_attribute("fov", "90")

        # spawn cameras (attached to ego)
        cam_front = world.spawn_actor(cam_front_bp, carla.Transform(carla.Location(x=1.5, z=2.4)), attach_to=ego)
        cam_third = world.spawn_actor(cam_third_bp, carla.Transform(carla.Location(x=-7, z=3), carla.Rotation(pitch=-10)), attach_to=ego)
        sensors += [cam_front, cam_third]

        cam_front.listen(make_camera_callback("front"))
        cam_third.listen(make_camera_callback("third"))

        # spawn other vehicles lightly
        spawn_points = carla_map.get_spawn_points()
        random.shuffle(spawn_points)
        vehicle_bps = blueprint_library.filter("vehicle.*")
        spawned_other = 0
        for sp in spawn_points:
            if spawned_other >= MAX_OTHER_VEHICLES:
                break
            try:
                if sp.location.distance(ego.get_location()) < 8.0:
                    continue
            except Exception:
                pass
            bp = random.choice(vehicle_bps)
            v = world.try_spawn_actor(bp, sp)
            if v:
                vehicles.append(v)
                spawned_other += 1
                try:
                    if tm:
                        v.set_autopilot(True, tm.get_port())
                    else:
                        v.set_autopilot(True)
                except Exception:
                    v.set_autopilot(True)
        logger.info("Spawned %d other vehicles", spawned_other)

        # optionally spawn walkers (keep them low)
        walker_bps = blueprint_library.filter("walker.pedestrian.*")
        walker_controller_bp = blueprint_library.find("controller.ai.walker")

        clock = pygame.time.Clock()
        running = True
        staged_walkers = []
        spawn_attempts = 0

        logger.info("Simulation running (async). ESC to quit.")

        # Watchdog baseline
        _last_frame_time = time.time()

        while running:
            for e in pygame.event.get():
                if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                    running = False

            # Poll current snapshot (async mode)
            try:
                snap = world.get_snapshot()
            except Exception as e:
                logger.warning("get_snapshot() failed: %s", e)
                snap = None

            # If no snapshot, wait briefly and continue
            if snap is None:
                time.sleep(0.05)
                continue

            # Watchdog: if no camera frames seen recently, exit and log
            if time.time() - _last_frame_time > NO_FRAME_TIMEOUT:
                logger.error("No camera frames in %.1f s -> exiting (watchdog).", NO_FRAME_TIMEOUT)
                break

            # Basic telemetry of ego
            try:
                ego_transform = ego.get_transform()
                ego_location = ego_transform.location
                vel = ego.get_velocity()
                ctrl = ego.get_control()
                speed_kmh = 3.6 * (vel.x**2 + vel.y**2 + vel.z**2)**0.5
                telemetry.append = telemetry.append if isinstance(telemetry, deque) else None
                telemetry.append([snap.frame, snap.timestamp.elapsed_seconds, speed_kmh,
                                  ctrl.steer, ctrl.throttle, ctrl.brake,
                                  ego_location.x, ego_location.y, ego_location.z])
            except Exception:
                pass

            # Stage jaywalkers occasionally (if enabled)
            if (not args.no_walkers) and snap.frame > 40 and snap.frame % 200 == 0 and (len(walkers) + len(staged_walkers) < MAX_CROSSERS):
                try:
                    ego_wp = carla_map.get_waypoint(ego_location)
                    future = ego_wp.next(JAYWALK_STAGING_DISTANCE)
                    if future:
                        future_wp = future[0]
                        side = random.choice([-1, 1])
                        spawn_tf = future_wp.transform
                        rv = future_wp.transform.get_right_vector()
                        try:
                            spawn_tf.location += rv * (random.uniform(3.0, 4.0) * side)
                        except Exception:
                            pass

                        spawn_wp = None
                        try:
                            spawn_wp = carla_map.get_waypoint(spawn_tf.location, project_to_road=True, lane_type=carla.LaneType.Any)
                        except Exception:
                            spawn_wp = None

                        if spawn_wp:
                            st = spawn_wp.transform
                            st.location.z += 1.0
                            walker_bp = random.choice(walker_bps)
                            walker = world.try_spawn_actor(walker_bp, st)
                            if walker:
                                try:
                                    ctrl = world.spawn_actor(walker_controller_bp, carla.Transform(), attach_to=walker)
                                except Exception:
                                    try:
                                        walker.destroy()
                                    except Exception:
                                        pass
                                    continue
                                dest = future_wp.transform.location
                                dest += -side * rv * random.uniform(3.0, 4.0)
                                staged_walkers.append((walker, ctrl, dest, JAYWALK_TRIGGER_DISTANCE))
                                spawn_attempts += 1
                except Exception as e:
                    logger.debug("walker staging error: %s", e)

            # Trigger staged walkers when close
            remaining = []
            for walker, ctrl, destination, trig in staged_walkers:
                try:
                    if walker.get_location().distance(ego_location) < trig:
                        try:
                            ctrl.start()
                            ctrl.go_to_location(destination)
                            ctrl.set_max_speed(random.uniform(1.0, 2.0))
                        except Exception as e:
                            logger.debug("controller command failed: %s", e)
                        walkers.append(walker)
                        walker_controllers.append(ctrl)
                        logger.info("Triggered walker id=%s", walker.id)
                    else:
                        remaining.append((walker, ctrl, destination, trig))
                except Exception:
                    try:
                        if walker and safe_is_alive(walker):
                            walker.destroy()
                    except Exception:
                        pass
            staged_walkers = remaining

            # Render HUD
            display.fill((0, 0, 0))
            if third_image:
                display.blit(third_image, (0, 0))
            if front_image:
                pip_w, pip_h = 160, 120
                pip_surface = pygame.transform.scale(front_image, (pip_w, pip_h))
                pip_x, pip_y = display_w - pip_w - 10, display_h - pip_h - 10
                display.blit(pip_surface, (pip_x, pip_y))
                pygame.draw.rect(display, (255,255,255), (pip_x-2, pip_y-2, pip_w+4, pip_h+4), 2)

            # HUD text
            try:
                font = pygame.font.Font(None, 24)
                info_text = f"frame={snap.frame} walkers={len(walkers)} queued_saves={save_queue.qsize()}"
                display.blit(font.render(info_text, True, (255,255,255)), (10, 10))
            except Exception:
                pass

            pygame.display.flip()
            clock.tick(SIM_FPS)  # limit main loop frequency

    except KeyboardInterrupt:
        logger.info("Interrupted by user")

    except Exception as e:
        logger.exception("Critical error in main loop: %s", e)

    finally:
        logger.info("Cleanup starting...")

        # Save telemetry (best-effort)
        try:
            if telemetry:
                with open(os.path.join(OUT_DIR, "telemetry.csv"), "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["frame","time_s","speed_kmh","steer","throttle","brake","x","y","z"])
                    writer.writerows(list(telemetry))
                logger.info("Telemetry saved")
        except Exception as e:
            logger.warning("Telemetry save failed: %s", e)

        # Finish background saves (no timeout argument on Queue.join)
        try:
            save_queue.join()
        except Exception:
            pass
        stop_saver.set()
        saver_thread.join(timeout=1.0)

        # Destroy actors via batch
        all_ids = []
        try:
            for a in sensors + walker_controllers + walkers + vehicles:
                try:
                    if a and safe_is_alive(a):
                        all_ids.append(a.id)
                except Exception:
                    pass
        except Exception:
            pass

        if all_ids:
            try:
                batch = [carla.command.DestroyActor(x) for x in all_ids]
                client.apply_batch_sync(batch, True)
            except Exception as e:
                logger.warning("Batch destroy failed: %s", e)
                # fallback per-actor destroy
                for a in sensors + walker_controllers + walkers + vehicles:
                    try:
                        if a and safe_is_alive(a):
                            a.destroy()
                    except Exception:
                        pass

        # restore original server settings if available
        try:
            if original_settings:
                world.apply_settings(original_settings)
        except Exception:
            pass

        pygame.quit()
        logger.info("Cleanup complete.")

if __name__ == "__main__":
    # pre-create some names used in the module scope
    clock = pygame.time.Clock()
    telemetry = deque(maxlen=MAX_TELEMETRY_ROWS)
    args = parse_args()
    # create camera callbacks with closures so we can pass "front"/"third"
    # NOTE: we must create them after parse_args() so callbacks obey flags like no_save / lowres
    # But make_camera_callback is stateless and fine here.
    main()
