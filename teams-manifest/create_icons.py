#!/usr/bin/env python3
"""
Create placeholder icons for Teams app manifest.
These are basic placeholders - replace with your actual bot branding.
"""

from PIL import Image, ImageDraw, ImageFont
import os

# Create color icon (192x192)
color_icon = Image.new('RGBA', (192, 192), (0, 0, 0, 0))
draw = ImageDraw.Draw(color_icon)

# Draw a gradient blue circle background
for i in range(96):
    color = (30 + i, 136 - i//2, 229)
    draw.ellipse([96-i, 96-i, 96+i, 96+i], fill=color + (255,))

# Draw "AI" text
try:
    # Try to use a system font
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
except:
    font = ImageFont.load_default()

text = "AI"
# Calculate text position to center it
bbox = draw.textbbox((0, 0), text, font=font)
text_width = bbox[2] - bbox[0]
text_height = bbox[3] - bbox[1]
position = ((192 - text_width) // 2, (192 - text_height) // 2 - 10)
draw.text(position, text, fill='white', font=font)

color_icon.save('color.png')
print("✅ Created color.png (192x192)")

# Create outline icon (32x32)
outline_icon = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
draw = ImageDraw.Draw(outline_icon)

# Draw white circle outline
draw.ellipse([2, 2, 30, 30], outline='white', width=2)

# Draw simple "AI" or bot symbol
try:
    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
except:
    font_small = ImageFont.load_default()

text = "AI"
bbox = draw.textbbox((0, 0), text, font=font_small)
text_width = bbox[2] - bbox[0]
text_height = bbox[3] - bbox[1]
position = ((32 - text_width) // 2, (32 - text_height) // 2 - 2)
draw.text(position, text, fill='white', font=font_small)

outline_icon.save('outline.png')
print("✅ Created outline.png (32x32)")

print("\n📦 Now create the Teams app package:")
print("   cd /workspaces/botserviceMultitenant/teams-manifest")
print("   zip ../teams-app.zip manifest.json color.png outline.png")
