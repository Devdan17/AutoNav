import carla
import random

client = carla.Client("localhost", 2000)
client.set_timeout(10.0)
world = client.get_world()

blueprint_library = world.get_blueprint_library()

# Pick a random vehicle blueprint
vehicle_bp = random.choice(blueprint_library.filter("vehicle.*"))

# Pick a spawn point
spawn_point = random.choice(world.get_map().get_spawn_points())

# Spawn vehicle
vehicle = world.spawn_actor(vehicle_bp, spawn_point)

print("Spawned vehicle:", vehicle.type_id)
