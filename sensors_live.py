import carla
import random
import os
import pygame
import numpy as np

def main():
    client = carla.Client("localhost", 2000)
    client.set_timeout(10.0)
    world = client.get_world()
    blueprint_library = world.get_blueprint_library()

    # Enable synchronous mode
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = 0.05  # 20 FPS
    world.apply_settings(settings)

    # --- Spawn a vehicle ---
    vehicle_bp = random.choice(blueprint_library.filter("vehicle.*"))
    spawn_point = random.choice(world.get_map().get_spawn_points())
    vehicle = world.try_spawn_actor(vehicle_bp, spawn_point)
    if vehicle is None:
        print("❌ Could not spawn vehicle, try again.")
        return
    print("✅ Vehicle spawned")

    # --- Camera sensor ---
    image_w, image_h = 800, 600
    camera_bp = blueprint_library.find("sensor.camera.rgb")
    camera_bp.set_attribute("image_size_x", str(image_w))
    camera_bp.set_attribute("image_size_y", str(image_h))
    camera_bp.set_attribute("fov", "90")

    camera_transform = carla.Transform(carla.Location(x=1.5, z=2.4))
    camera = world.spawn_actor(camera_bp, camera_transform, attach_to=vehicle)

    # Output directory
    if not os.path.exists("_out"):
        os.makedirs("_out")

    # Pygame setup
    pygame.init()
    display = pygame.display.set_mode((image_w, image_h))
    pygame.display.set_caption("CARLA Camera View")
    clock = pygame.time.Clock()

    # Shared state for last frame
    image_surface = [None]

    def process_img(image):
        # Save to disk
        image.save_to_disk("_out/%06d.png" % image.frame)
        # Convert to numpy for pygame
        array = np.frombuffer(image.raw_data, dtype=np.uint8)
        array = array.reshape((image.height, image.width, 4))  # RGBA
        surface = pygame.surfarray.make_surface(array[:, :, :3].swapaxes(0, 1))
        image_surface[0] = surface

    camera.listen(lambda img: process_img(img))

    # --- Main loop ---
    try:
        running = True
        while running:
            world.tick()  # advance simulation one step

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            if image_surface[0] is not None:
                display.blit(image_surface[0], (0, 0))

            pygame.display.flip()
            clock.tick(30)

    except KeyboardInterrupt:
        print("\n🛑 Stopping simulation...")

    finally:
        print("Cleaning up...")
        camera.stop()
        camera.destroy()
        vehicle.destroy()

        # Restore async mode
        settings = world.get_settings()
        settings.synchronous_mode = False
        settings.fixed_delta_seconds = None
        world.apply_settings(settings)

        pygame.quit()
        print("✅ Cleanup complete")

if __name__ == "__main__":
    main()
