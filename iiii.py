import carla
client = carla.Client("localhost", 2000)
world = client.get_world()
print("TICK")
world.tick()
print("OK")
