import carla
import random
import time
import numpy as np
import pygame
import os
import csv

# =================== Initialize Pygame ===================
pygame.init()
WIDTH, HEIGHT = 1280, 720
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Autonomous Ego Car")
clock = pygame.time.Clock()
font = pygame.font.SysFont("Arial", 22)

# =================== Connect to CARLA ===================
client = carla.Client('localhost', 2000)
client.set_timeout(10.0)
world = client.get_world()

blueprint_library = world.get_blueprint_library()

# =================== Spawn Ego Vehicle ===================
vehicle_bp = blueprint_library.filter('model3')[0]
spawn_point = random.choice(world.get_map().get_spawn_points())
vehicle = world.try_spawn_actor(vehicle_bp, spawn_point)

if vehicle is None:
    print("❌ Could not spawn vehicle, try again.")
    pygame.quit()
    exit()

# Enable autopilot (lane following)
vehicle.set_autopilot(True)

# =================== Camera Sensors ===================
camera_bp = blueprint_library.find('sensor.camera.rgb')
camera_bp.set_attribute('image_size_x', str(WIDTH // 2))
camera_bp.set_attribute('image_size_y', str(HEIGHT))
camera_bp.set_attribute('fov', '90')

# Front Camera
front_camera_transform = carla.Transform(carla.Location(x=1.5, z=2.4))
front_camera = world.spawn_actor(camera_bp, front_camera_transform, attach_to=vehicle)

# Third Person Camera
third_person_transform = carla.Transform(carla.Location(x=-5, z=3), carla.Rotation(pitch=-15))
third_camera = world.spawn_actor(camera_bp, third_person_transform, attach_to=vehicle)

front_image = None
third_image = None

# =================== Vehicle State Tracking ===================
stop_start_time = None
total_stop_time = 0.0
brake_start_time = None
total_brake_time = 0.0
detection_start_time = None
detection_duration = 0.0

# These are global variables that need to be declared as such
# outside of the function they are modified in.
accel_x, accel_y, accel_z = 0.0, 0.0, 0.0
velocity_prev = carla.Vector3D(0, 0, 0)
last_time = time.time()
start_time = time.time()
distance_travelled = 0.0
last_location = vehicle.get_location()

# =================== CSV Data Logging Setup ===================
output_dir = "_out"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

csv_file_path = os.path.join(output_dir, 'simulation_data.csv')
csv_file = open(csv_file_path, 'w', newline='')
csv_writer = csv.writer(csv_file)
csv_writer.writerow(['Time (s)', 'Speed (km/h)', 'Distance Travelled (m)', 'Total Stop Time (s)', 
                     'Total Brake Time (s)', 'Detection Duration (s)', 'Accel X (m/s²)', 'Accel Y (m/s²)', 'Accel Z (m/s²)'])

# =================== Helper Functions ===================
def process_img(image, view="front"):
    global front_image, third_image
    i = np.array(image.raw_data)
    i2 = i.reshape((image.height, image.width, 4))
    i3 = i2[:, :, :3]
    i3 = np.rot90(i3)
    i3 = np.flipud(i3)

    surf = pygame.surfarray.make_surface(i3)
    if view == "front":
        front_image = surf
    else:
        third_image = surf

front_camera.listen(lambda image: process_img(image, "front"))
third_camera.listen(lambda image: process_img(image, "third"))

# =================== Main Loop ===================
try:
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill((0, 0, 0))

        if front_image:
            screen.blit(front_image, (0, 0))  # Left side

        if third_image:
            screen.blit(third_image, (WIDTH // 2, 0))  # Right side

        # =================== Vehicle Info & Data Tracking ===================
        # Time and Distance
        current_time = time.time()
        elapsed_time = current_time - start_time
        
        current_location = vehicle.get_location()
        distance_travelled += current_location.distance(last_location)
        last_location = current_location
        
        velocity = vehicle.get_velocity()
        speed = np.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2) * 3.6  # km/h
        control = vehicle.get_control()

        # Stop time tracking
        if speed < 0.1:
            if stop_start_time is None:
                stop_start_time = time.time()
            total_stop_time = time.time() - stop_start_time
        else:
            stop_start_time = None

        # Brake duration tracking
        if control.brake > 0:
            if brake_start_time is None:
                brake_start_time = time.time()
            total_brake_time = time.time() - brake_start_time
            # Simulate a "detection" event when brake is applied
            if detection_start_time is None:
                detection_start_time = time.time()
            detection_duration = time.time() - detection_start_time
        else:
            brake_start_time = None
            detection_start_time = None # Reset detection timer when not braking

        # Acceleration estimation
        # This is where the syntax error was. By declaring the variables at the top of the script,
        # you no longer need the 'global' keyword here.
        current_time_for_accel = time.time()
        dt = current_time_for_accel - last_time
        if dt > 0:
            accel_x = (velocity.x - velocity_prev.x) / dt
            accel_y = (velocity.y - velocity_prev.y) / dt
            accel_z = (velocity.z - velocity_prev.z) / dt
        velocity_prev = velocity
        last_time = current_time_for_accel

        # =================== Write Data to CSV ===================
        csv_writer.writerow([
            f"{elapsed_time:.2f}", 
            f"{speed:.2f}",
            f"{distance_travelled:.2f}",
            f"{total_stop_time:.2f}", 
            f"{total_brake_time:.2f}",
            f"{detection_duration:.2f}",
            f"{accel_x:.2f}",
            f"{accel_y:.2f}",
            f"{accel_z:.2f}"
        ])

        # =================== Display Info ===================
        text_surface = font.render(f"Speed: {speed:.2f} km/h", True, (255, 255, 255))
        screen.blit(text_surface, (10, 10))

        text_surface = font.render(f"Distance: {distance_travelled:.2f} m", True, (255, 255, 255))
        screen.blit(text_surface, (10, 40))

        text_surface = font.render(f"Total Stop Time: {total_stop_time:.1f} s", True, (255, 255, 255))
        screen.blit(text_surface, (10, 70))

        text_surface = font.render(f"Brake Duration: {total_brake_time:.1f} s", True, (255, 255, 255))
        screen.blit(text_surface, (10, 100))
        
        text_surface = font.render(f"Detection Time: {detection_duration:.1f} s", True, (255, 255, 255))
        screen.blit(text_surface, (10, 130))

        text_surface = font.render(f"Accel (x,y,z): ({accel_x:.2f}, {accel_y:.2f}, {accel_z:.2f}) m/s²", True, (255, 255, 255))
        screen.blit(text_surface, (10, 160))
        
        text_surface = font.render(f"Elapsed Time: {elapsed_time:.2f} s", True, (255, 255, 255))
        screen.blit(text_surface, (10, 190))

        pygame.display.flip()
        clock.tick(30)

finally:
    print("Destroying actors...")
    front_camera.destroy()
    third_camera.destroy()
    vehicle.destroy()
    pygame.quit()
    csv_file.close()
    print("✅ CSV data saved to simulation_data.csv")