#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from PIL import Image, ImageTk
import tkinter as tk

# Test 1: Check if files exist
ui_bg = "ui_background.png"
side_box = "side_box.png"

print(f"[TEST] Checking if {ui_bg} exists: {os.path.exists(ui_bg)}")
print(f"[TEST] Checking if {side_box} exists: {os.path.exists(side_box)}")

# Test 2: Try to open and resize them
root = tk.Tk()
root.title("Image Loading Test")
root.geometry("400x300")

try:
    # Load ui_background
    print("[TEST] Loading ui_background.png...")
    img1 = Image.open(ui_bg)
    print(f"[TEST] Original size: {img1.size}, mode: {img1.mode}")
    
    img1_resized = img1.convert("RGBA").resize((400, 600), Image.Resampling.LANCZOS)
    print(f"[TEST] Resized to: {img1_resized.size}")
    
    img1_rgb = img1_resized.convert("RGB")
    photo1 = ImageTk.PhotoImage(img1_rgb)
    photo1.pil_image = img1_rgb
    print(f"[TEST] PhotoImage created for ui_background")
    
    # Load side_box
    print("[TEST] Loading side_box.png...")
    img2 = Image.open(side_box)
    print(f"[TEST] Original size: {img2.size}, mode: {img2.mode}")
    
    img2_resized = img2.convert("RGBA").resize((270, 270), Image.Resampling.LANCZOS)
    print(f"[TEST] Resized to: {img2_resized.size}")
    
    img2_rgb = img2_resized.convert("RGB")
    photo2 = ImageTk.PhotoImage(img2_rgb)
    photo2.pil_image = img2_rgb
    print(f"[TEST] PhotoImage created for side_box")
    
    # Display them
    canvas = tk.Canvas(root, width=400, height=300, bg="black")
    canvas.pack()
    canvas.create_image(200, 150, image=photo1)
    canvas.create_image(50, 50, image=photo2)
    
    print("[TEST] ✓ All images loaded successfully!")
    root.after(3000, root.quit)
    
except Exception as e:
    print(f"[TEST] ✗ Error: {e}")
    import traceback
    traceback.print_exc()
    
root.mainloop()
