#!/usr/bin/env python3
"""
Simplest possible MLX90640 viewer — runs on the OrangePi with HDMI output.
Uses the adafruit library (already installed) + matplotlib.

    pip3 install matplotlib
    BLINKA_MCP2221=1 python3 view_thermal.py   # if board detection fails
    python3 view_thermal.py                     # try this first
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import board
import busio
import adafruit_mlx90640

# ── sensor init ──────────────────────────────────────────────────────────────
i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
mlx = adafruit_mlx90640.MLX90640(i2c)
mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_4_HZ

frame = [0.0] * 768

# ── plot setup ───────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 7))
fig.patch.set_facecolor('black')
ax.axis('off')

data = np.zeros((24, 32))
img  = ax.imshow(data, cmap='inferno', interpolation='bilinear',
                 vmin=20, vmax=35, aspect='auto')

cbar = fig.colorbar(img, ax=ax, fraction=0.046, pad=0.04)
cbar.set_label('°C', color='white')
cbar.ax.yaxis.set_tick_params(color='white')
plt.setp(cbar.ax.yaxis.get_ticklabels(), color='white')

title = ax.set_title('MLX90640', color='white', fontsize=14)
plt.tight_layout()

# ── update loop ──────────────────────────────────────────────────────────────
def update(_):
    try:
        mlx.getFrame(frame)
    except Exception as e:
        print(f"frame error: {e}")
        return img,

    data = np.array(frame).reshape((24, 32))
    data = np.fliplr(data)   # mirror horizontally

    mn, mx = data.min(), data.max()
    img.set_data(data)
    img.set_clim(vmin=mn, vmax=mx)   # auto-scale to scene
    title.set_text(f'MLX90640   min={mn:.1f}°C  max={mx:.1f}°C')
    return img,

ani = animation.FuncAnimation(fig, update, interval=300, blit=False)
plt.show()
