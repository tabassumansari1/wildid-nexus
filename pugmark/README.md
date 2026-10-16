# Pugmark

Re-identify individual wild animals from photos and video.

A waterhole sighting is not an identity. Two tigers share a skeleton, a stance, and a way of drinking. Pugmark ignores pose and mouth movement. It matches the geometry of the coat — stripes, spots, scars — and reports whether the files you attached are the same individual, different individuals, or too unclear to call.

Jungle mein jo sher aaj dikha, aur jo kal: woh ek hai, ya do? Yahi sawaal hai.

## Run it

Python 3.10, 3.11, 3.12, or 3.13. The first run downloads the image libraries (about 80 MB).

**Windows** — double-click `setup.bat`, then open http://127.0.0.1:8000

**macOS / Linux**

```bash
chmod +x setup.sh
./setup.sh
```

Then open http://127.0.0.1:8000

Manual equivalent:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Use it

1. Landing page → **Start connecting**.
2. Drop two or more photos and/or videos (up to 12 files, 40 MB each).
3. **Compare markings**. The field report groups files into individuals and shows the point correspondences.

No animals handy? On the connect page, load a reference set:

- **Same individual, two shots** — one coat, re-photographed (shift, brightness, new background).
- **Two individuals** — two different coats.
- **Three files, mixed** — the repeat plus a stranger.

Then run your own camera-trap or patrol photos. Patterned animals (tiger, leopard, zebra, giraffe) in clear light work best. A dark, blurred, or edge-on frame is reported as inconclusive instead of a forced answer.

## How the backend decides

`identify/engine.py`

1. Stills are loaded as-is. Video is sampled and the sharpest frames are kept (`ffmpeg` is inside the OpenCV build; you do not install it separately).
2. Spectral saliency proposes an animal region so the waterhole and the trees are not the thing being matched.
3. SIFT marking points are extracted (full frame and the crop).
4. Candidates pass a Lowe ratio test, then RANSAC affine. Only points that fit one geometric transform survive.
5. Verdict:
   - **Same** — enough verified correspondences (or the file is a trivial re-export of the same frame).
   - **Different** — the geometry does not agree, and both views were sharp enough to trust a rejection.
   - **Inconclusive** — too few stable points to be either sure or dismissive.
6. Files are grouped only when every cross-pair in a group has a supported match; one conflicting comparison blocks a transitive merge.

Species names are estimates, separate from individual identity. Clear coat-pattern cues or an explicit species name in the filename can provide a label; ambiguous images stay **Wild Individual** rather than being forced into a species. The visual species heuristic is not a trained species-recognition model, so verify that label in the field report.

This is the HotSpotter family of wildlife re-ID (local features + geometry), not human face recognition and not a chat model guessing from a description. It will not be right 100% of the time. Viewpoint, occlusion and plain coats are genuinely hard. The report shows the lines so a person can check the machine.

## Layout

- `/` landing
- `/connect/` upload
- `/report/<id>/` result, stored in SQLite
- `samples` are written into `static/samples/` by the tests’ coat generator; they ship with this folder

Login, signup, password reset, about, help, terms and privacy are intentionally not in this build.
