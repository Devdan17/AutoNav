import carla

# Connect to server (CARLA must already be running)
client = carla.Client("localhost", 2000)
client.set_timeout(10.0)

# Get world
world = client.load_world('Town03')

print("Connected to CARLA:", world.get_map().name)
