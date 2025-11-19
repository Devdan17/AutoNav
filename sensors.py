import carla
import random
import os

def main():
    client = carla.Client("localhost", 2000)
    client.set_timeout(10.0)
    world = client.get_world()
    blueprint_library = world.get_blueprint_library()

    # --- Spawn a vehicle (ego vehicle) ---
    vehicle_bp = random.choice(blueprint_library.filter("vehicle.*"))
    spawn_point = random.choice(world.get_map().get_spawn_points())
    vehicle = world.try_spawn_actor(vehicle_bp, spawn_point)

    if vehicle is None:
        print("❌ Could not spawn vehicle, try again.")
        return

    print("✅ Vehicle spawned")

    # --- Camera sensor ---
    camera_bp = blueprint_library.find("sensor.camera.rgb")
    camera_bp.set_attribute("image_size_x", "800")
    camera_bp.set_attribute("image_size_y", "600")
    camera_bp.set_attribute("fov", "90")

    # Camera placement: 1.5m forward, 2.4m above the car
    camera_transform = carla.Transform(carla.Location(x=1.5, z=2.4))
    camera = world.spawn_actor(camera_bp, camera_transform, attach_to=vehicle)

    # --- Save images to disk ---
    if not os.path.exists("_out"):
        os.makedirs("_out")

    camera.listen(lambda image: image.save_to_disk("_out/%06d.png" % image.frame))
    print("📸 Camera attached, images will be saved to _out/")

    # --- Run until stopped ---
    try:
        while True:
            world.tick()
    except KeyboardInterrupt:
        print("\n🛑 Stopping simulation...")
    finally:
        camera.stop()
        camera.destroy()
        vehicle.destroy()
        print("✅ Cleanup complete")

if __name__ == "__main__":
    main()
