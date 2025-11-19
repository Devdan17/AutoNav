# analyze_data.py
# Requires: pandas, matplotlib, seaborn

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# --- Configuration ---
DATA_DIR = "carla_dataset"
TELEMETRY_FILE = os.path.join(DATA_DIR, "telemetry.csv")
OUTPUT_DIR = "output_graphs"

# Create a directory to save the graphs
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Step 1: Load the Data ---
try:
    df = pd.read_csv(TELEMETRY_FILE)
    print("✅ Telemetry data loaded successfully!")
    print("\nData summary:")
    print(df.describe())
except FileNotFoundError:
    print(f"❌ Error: The file '{TELEMETRY_FILE}' was not found.")
    print("Please make sure you have run the CARLA simulation script first and the data was saved.")
    exit()

# Set a nice style for the plots
sns.set_theme(style="whitegrid")

# --- Step 2: Create and Save Graphs ---

# Graph 1: Speed Over Time
print("\nGenerating graph 1: Speed Over Time...")
plt.figure(figsize=(15, 7))
plt.plot(df['time_s'], df['speed_kmh'], label='Speed (km/h)', color='dodgerblue')
plt.title('Ego Vehicle Speed Over Time', fontsize=16)
plt.xlabel('Time (seconds)', fontsize=12)
plt.ylabel('Speed (km/h)', fontsize=12)
plt.legend()
plt.grid(True)
plt.savefig(os.path.join(OUTPUT_DIR, '1_speed_over_time.png'))
plt.close() # Close the plot to free up memory
print(f" -> Saved to {os.path.join(OUTPUT_DIR, '1_speed_over_time.png')}")

# Graph 2: Control Inputs Over Time (Throttle, Brake, Steer)
print("Generating graph 2: Control Inputs Over Time...")
fig, axes = plt.subplots(3, 1, figsize=(15, 12), sharex=True)
fig.suptitle('Autopilot Control Inputs Over Time', fontsize=16)

# Throttle
axes[0].plot(df['time_s'], df['throttle'], label='Throttle', color='green')
axes[0].set_ylabel('Throttle', fontsize=12)
axes[0].set_ylim(0, 1)
axes[0].legend()

# Brake
axes[1].plot(df['time_s'], df['brake'], label='Brake', color='red')
axes[1].set_ylabel('Brake', fontsize=12)
axes[1].set_ylim(0, 1)
axes[1].legend()

# Steering
axes[2].plot(df['time_s'], df['steer'], label='Steer', color='purple')
axes[2].set_ylabel('Steer', fontsize=12)
axes[2].set_ylim(-1.1, 1.1)
axes[2].axhline(0, color='black', linewidth=0.5, linestyle='--') # Add a zero line
axes[2].legend()

axes[2].set_xlabel('Time (seconds)', fontsize=12)
plt.tight_layout(rect=[0, 0.03, 1, 0.95])
plt.savefig(os.path.join(OUTPUT_DIR, '2_control_inputs.png'))
plt.close()
print(f" -> Saved to {os.path.join(OUTPUT_DIR, '2_control_inputs.png')}")

# Graph 3: Vehicle's Path (Bird's-Eye View)
print("Generating graph 3: Vehicle's Path...")
plt.figure(figsize=(10, 10))
plt.plot(df['x'], df['y'], color='black', linewidth=2)
# Mark the start and end points
plt.scatter(df['x'].iloc[0], df['y'].iloc[0], color='green', s=150, zorder=5, label='Start')
plt.scatter(df['x'].iloc[-1], df['y'].iloc[-1], color='red', s=150, zorder=5, label='End')
plt.title("Vehicle's Path (Bird's-Eye View)", fontsize=16)
plt.xlabel("X Coordinate (meters)", fontsize=12)
plt.ylabel("Y Coordinate (meters)", fontsize=12)
plt.legend()
plt.axis('equal') # Ensure the X and Y axes have the same scale
plt.grid(True)
plt.savefig(os.path.join(OUTPUT_DIR, '3_vehicle_path.png'))
plt.close()
print(f" -> Saved to {os.path.join(OUTPUT_DIR, '3_vehicle_path.png')}")

# Graph 4: Distribution of Speed (Histogram)
print("Generating graph 4: Speed Distribution...")
plt.figure(figsize=(12, 6))
sns.histplot(df['speed_kmh'], kde=True, bins=30, color='teal')
avg_speed = df['speed_kmh'].mean()
plt.axvline(avg_speed, color='red', linestyle='--', label=f'Average Speed: {avg_speed:.2f} km/h')
plt.title('Distribution of Vehicle Speed', fontsize=16)
plt.xlabel('Speed (km/h)', fontsize=12)
plt.ylabel('Frequency', fontsize=12)
plt.legend()
plt.savefig(os.path.join(OUTPUT_DIR, '4_speed_distribution.png'))
plt.close()
print(f" -> Saved to {os.path.join(OUTPUT_DIR, '4_speed_distribution.png')}")

print("\n✅ All graphs have been generated and saved in the 'output_graphs' folder.")