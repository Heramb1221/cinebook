"""
Generates original, copyright-free poster artwork for the demo catalogue.
Each poster is a unique abstract SVG composition (gradient field + geometric
motif + Bebas-Neue-style title block) so the app has zero dependency on
external poster images and zero IP/copyright risk.
"""
import os

OUT_DIR = "/home/claude/movie-booking/frontend/posters"
os.makedirs(OUT_DIR, exist_ok=True)

# Each entry: id, title, short tag, two-color gradient, motif type
MOVIES = [
    {
        "id": "tt1375666", "title": "DEEP DRIFT", "tag": "REALITY IS A CHOICE",
        "c1": "#1B2A4A", "c2": "#0B0B0F", "accent": "#FFB800", "motif": "stairs",
    },
    {
        "id": "tt0816692", "title": "BEYOND THE STARS", "tag": "MANKIND'S NEXT STEP",
        "c1": "#1A1430", "c2": "#0B0B0F", "accent": "#FF8A3D", "motif": "orbit",
    },
    {
        "id": "tt15398776", "title": "CHAIN REACTION", "tag": "THE WORLD FOREVER CHANGES",
        "c1": "#3A1212", "c2": "#0B0B0F", "accent": "#E0263F", "motif": "blast",
    },
    {
        "id": "tt11304740", "title": "VENDETTA", "tag": "ONE MAN. ONE MISSION.",
        "c1": "#241313", "c2": "#0B0B0F", "accent": "#FFB800", "motif": "shatter",
    },
    {
        "id": "tt9362722", "title": "MULTIVERSE", "tag": "EVERY HERO HAS A STORY",
        "c1": "#1A0F2E", "c2": "#0B0B0F", "accent": "#C77DFF", "motif": "web",
    },
    {
        "id": "tt6443346", "title": "HIDDEN NATION", "tag": "FOREVER",
        "c1": "#0F1F1C", "c2": "#0B0B0F", "accent": "#2ECC71", "motif": "panther",
    },
]


def motif_svg(motif, accent):
    if motif == "stairs":
        return "".join(
            f'<rect x="{40+i*30}" y="{520-i*45}" width="220" height="14" fill="{accent}" opacity="{0.5 - i*0.06}"/>'
            for i in range(7)
        )
    if motif == "orbit":
        return f"""
        <circle cx="200" cy="380" r="140" fill="none" stroke="{accent}" stroke-width="2" opacity="0.5"/>
        <circle cx="200" cy="380" r="95" fill="none" stroke="{accent}" stroke-width="1.5" opacity="0.35"/>
        <circle cx="320" cy="280" r="10" fill="{accent}"/>
        """
    if motif == "blast":
        rays = "".join(
            f'<line x1="200" y1="380" x2="{200+220*__import__("math").cos(i)}" y2="{380+220*__import__("math").sin(i)}" stroke="{accent}" stroke-width="2" opacity="0.4"/>'
            for i in [x * 0.523 for x in range(12)]
        )
        return f'<circle cx="200" cy="380" r="60" fill="{accent}" opacity="0.25"/>' + rays
    if motif == "shatter":
        return "".join(
            f'<polygon points="{60+i*25},{200+i*20} {120+i*25},{180+i*15} {100+i*25},{320+i*10}" fill="{accent}" opacity="{0.15+i*0.04}"/>'
            for i in range(8)
        )
    if motif == "web":
        lines = "".join(
            f'<line x1="200" y1="100" x2="{200+300*__import__("math").cos(i)}" y2="{100+300*__import__("math").sin(i)}" stroke="{accent}" stroke-width="1" opacity="0.3"/>'
            for i in [x * 0.785 for x in range(8)]
        )
        arcs = "".join(
            f'<circle cx="200" cy="100" r="{40*i}" fill="none" stroke="{accent}" stroke-width="1" opacity="0.25"/>'
            for i in range(1, 8)
        )
        return lines + arcs
    if motif == "panther":
        return f"""
        <polygon points="200,180 260,320 200,420 140,320" fill="{accent}" opacity="0.18"/>
        <circle cx="200" cy="300" r="120" fill="none" stroke="{accent}" stroke-width="2" opacity="0.4"/>
        """
    return ""


def build_poster(m):
    svg = f'''<svg width="400" height="600" viewBox="0 0 400 600" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{m['c1']}"/>
      <stop offset="100%" stop-color="{m['c2']}"/>
    </linearGradient>
    <linearGradient id="vign" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#000000" stop-opacity="0"/>
      <stop offset="100%" stop-color="#000000" stop-opacity="0.65"/>
    </linearGradient>
  </defs>
  <rect width="400" height="600" fill="url(#bg)"/>
  <g>{motif_svg(m['motif'], m['accent'])}</g>
  <rect width="400" height="600" fill="url(#vign)"/>
  <rect x="0" y="0" width="400" height="600" fill="none" stroke="{m['accent']}" stroke-opacity="0.25" stroke-width="6"/>
  <text x="200" y="500" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" font-weight="900" font-size="{38 if len(m['title'])<10 else 28}" fill="#F5F5F0" letter-spacing="2">{m['title']}</text>
  <text x="200" y="530" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" letter-spacing="3" fill="{m['accent']}">{m['tag']}</text>
  <rect x="170" y="552" width="60" height="3" fill="{m['accent']}" opacity="0.6"/>
</svg>'''
    path = os.path.join(OUT_DIR, f"{m['id']}.svg")
    with open(path, "w") as f:
        f.write(svg)
    return path


for m in MOVIES:
    p = build_poster(m)
    print("wrote", p)
