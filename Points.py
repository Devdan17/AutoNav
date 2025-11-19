import carla
client = carla.Client("localhost", 2000)
client.set_timeout(5.0)
world = client.get_world()
for i, sp in enumerate(world.get_map().get_spawn_points()):
    print(i, sp)
