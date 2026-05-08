#!/usr/bin/env python3
"""
Minimal RFID Music Player to test image loading
"""
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageFilter

APP_W, APP_H = 720, 900
UI_BG_IMAGE = "ui_background.png"
SIDE_BOX_IMAGE = "side_box.png"
WIDGET_BG = "#111B2D"
TEXT = "#F3F7FF"

class MinimalRFIDPlayer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RFID Music Player - Minimal Test")
        self.geometry(f"{APP_W}x{APP_H}")
        self.configure(bg=WIDGET_BG)
        self.resizable(False, False)
        
        # Store image references
        self.images = {}
        
        self.create_widgets()
        self.deiconify()
        self.lift()
        self.focus_force()
    
    def create_widgets(self):
        # Create canvas
        self.canvas = tk.Canvas(self, width=APP_W, height=APP_H, 
                               highlightthickness=0, bd=0, bg=WIDGET_BG)
        self.canvas.pack(fill="both", expand=True)
        
        try:
            # Load and display background image
            print("[DEBUG] Loading background image...")
            bg_img = Image.open(UI_BG_IMAGE)
            print(f"[DEBUG] Background: {bg_img.size}, {bg_img.mode}")
            
            bg_rgba = bg_img.convert("RGBA").resize((APP_W, APP_H), Image.Resampling.LANCZOS)
            bg_rgb = bg_rgba.convert("RGB")
            
            bg_photo = ImageTk.PhotoImage(bg_rgb)
            bg_photo.pil_image = bg_rgb
            
            # Keep strong reference
            self.images['bg'] = bg_photo
            
            self.canvas.create_image(APP_W // 2, APP_H // 2, image=bg_photo, anchor="center")
            print("[DEBUG] Background image placed")
            
            # Load and display side box image
            print("[DEBUG] Loading side box image...")
            side_img = Image.open(SIDE_BOX_IMAGE)
            print(f"[DEBUG] Side box: {side_img.size}, {side_img.mode}")
            
            side_rgba = side_img.convert("RGBA").resize((270, 270), Image.Resampling.LANCZOS)
            side_rgb = side_rgba.convert("RGB")
            
            side_photo = ImageTk.PhotoImage(side_rgb)
            side_photo.pil_image = side_rgb
            
            # Keep strong reference
            self.images['side'] = side_photo
            
            self.canvas.create_image(150, 200, image=side_photo)
            print("[DEBUG] Side box image placed")
            
            # Add text
            self.canvas.create_text(APP_W // 2, APP_H - 50, 
                                   text="✓ If you see images, images are loading correctly!",
                                   fill=TEXT, font=("Segoe UI", 14))
            print("[DEBUG] ✓ All images loaded successfully!")
            
        except Exception as e:
            print(f"[DEBUG] ✗ Error: {e}")
            import traceback
            traceback.print_exc()
            self.canvas.create_text(APP_W // 2, APP_H // 2,
                                   text=f"Error: {e}",
                                   fill="red", font=("Arial", 12))

if __name__ == "__main__":
    app = MinimalRFIDPlayer()
    app.after(10000, app.quit)  # Close after 10 seconds
    app.mainloop()
