#!/usr/bin/env python3
"""
Comprehensive test to verify all images load and display correctly
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from PIL import Image, ImageTk, ImageDraw, ImageFilter
import tkinter as tk

# Image paths
UI_BG_IMAGE = "ui_background.png"
SIDE_BOX_IMAGE = "side_box.png"

APP_W, APP_H = 720, 900

def test_image_loading():
    """Test that all images can be loaded and processed"""
    print("=" * 60)
    print("TESTING IMAGE LOADING")
    print("=" * 60)
    
    # Test UI background
    print(f"\n1. Testing {UI_BG_IMAGE}...")
    if not os.path.exists(UI_BG_IMAGE):
        print(f"   ✗ File not found!")
        return False
    
    try:
        img = Image.open(UI_BG_IMAGE)
        print(f"   ✓ Loaded: {img.format}, {img.size}, {img.mode}")
        
        img_rgba = img.convert("RGBA")
        print(f"   ✓ Converted to RGBA")
        
        img_resized = img_rgba.resize((APP_W, APP_H), Image.Resampling.LANCZOS)
        print(f"   ✓ Resized to {img_resized.size}")
        
        img_rgb = img_resized.convert("RGB")
        print(f"   ✓ Converted to RGB")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    # Test side box
    print(f"\n2. Testing {SIDE_BOX_IMAGE}...")
    if not os.path.exists(SIDE_BOX_IMAGE):
        print(f"   ✗ File not found!")
        return False
    
    try:
        img = Image.open(SIDE_BOX_IMAGE)
        print(f"   ✓ Loaded: {img.format}, {img.size}, {img.mode}")
        
        img_rgba = img.convert("RGBA")
        print(f"   ✓ Converted to RGBA")
        
        img_resized = img_rgba.resize((270, 270), Image.Resampling.LANCZOS)
        print(f"   ✓ Resized to {img_resized.size}")
        
        img_rgb = img_resized.convert("RGB")
        print(f"   ✓ Converted to RGB")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    print("\n✓ All image loading tests passed!")
    return True


def test_photoimage_creation():
    """Test that PhotoImage objects can be created and persist"""
    print("\n" + "=" * 60)
    print("TESTING PHOTOIMAGE CREATION")
    print("=" * 60)
    
    # Create root window
    root = tk.Tk()
    root.title("PhotoImage Test")
    root.geometry(f"{APP_W}x{APP_H}")
    
    images = {}
    
    try:
        # Test background image
        print(f"\n1. Creating PhotoImage for {UI_BG_IMAGE}...")
        bg_rgba = Image.open(UI_BG_IMAGE).convert("RGBA").resize((APP_W, APP_H), Image.Resampling.LANCZOS)
        bg_rgb = bg_rgba.convert("RGB")
        bg_photo = ImageTk.PhotoImage(bg_rgb)
        bg_photo.pil_image = bg_rgb  # Keep reference
        images['bg'] = {'photo': bg_photo, 'pil': bg_rgb}
        print(f"   ✓ PhotoImage created: {type(bg_photo)}")
        
        # Test overlay
        print(f"\n2. Creating PhotoImage for overlay...")
        overlay_rgba = Image.new("RGBA", (APP_W, APP_H), (0, 0, 0, 55))
        overlay_pil = overlay_rgba.convert("RGB")
        overlay_photo = ImageTk.PhotoImage(overlay_pil)
        overlay_photo.pil_image = overlay_pil
        images['overlay'] = {'photo': overlay_photo, 'pil': overlay_pil}
        print(f"   ✓ PhotoImage created: {type(overlay_photo)}")
        
        # Test side box
        print(f"\n3. Creating PhotoImage for {SIDE_BOX_IMAGE}...")
        side_rgba = Image.open(SIDE_BOX_IMAGE).convert("RGBA").resize((270, 270), Image.Resampling.LANCZOS)
        side_rgb = side_rgba.convert("RGB")
        side_photo = ImageTk.PhotoImage(side_rgb)
        side_photo.pil_image = side_rgb
        images['side'] = {'photo': side_photo, 'pil': side_rgb}
        print(f"   ✓ PhotoImage created: {type(side_photo)}")
        
        # Create canvas and display images
        print(f"\n4. Creating canvas and displaying images...")
        canvas = tk.Canvas(root, width=APP_W, height=APP_H, bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        
        # Display background
        canvas.create_image(APP_W // 2, APP_H // 2, image=bg_photo, anchor="center", tags="bg")
        print(f"   ✓ Background image placed on canvas")
        
        # Display overlay
        canvas.create_image(APP_W // 2, APP_H // 2, image=overlay_photo, tags="overlay")
        print(f"   ✓ Overlay image placed on canvas")
        
        # Display side box
        canvas.create_image(100, 100, image=side_photo, tags="side")
        print(f"   ✓ Side box image placed on canvas")
        
        # Display some text
        canvas.create_text(APP_W // 2, APP_H // 2, text="If you see images, test PASSED ✓", 
                          fill="white", font=("Arial", 14))
        
        print("\n✓ All PhotoImage tests passed!")
        print("Window will close in 5 seconds...")
        
        # Keep references alive
        root._images = images
        
        root.after(5000, root.quit)
        root.mainloop()
        
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        root.destroy()
        return False
    
    return True


if __name__ == "__main__":
    # Test 1: Image loading
    if not test_image_loading():
        sys.exit(1)
    
    # Test 2: PhotoImage creation and display
    if not test_photoimage_creation():
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)
