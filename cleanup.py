import carla
client = carla.Client("localhost", 2000)
client.set_timeout(5.0)
world = client.get_world()

actors = world.get_actors()
count = 0
for a in actors:
    if "vehicle" in a.type_id or "walker" in a.type_id:
        try:
            a.destroy()
            count += 1
        except:
            pass

print("Destroyed:", count, "actors.")
