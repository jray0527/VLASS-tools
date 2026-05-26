import os
import re
import csv
import requests
import wget
import numpy as np
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from astropy.io import fits
from astropy.wcs import WCS

#######################################

#change these for ep1-4

epname = "E3"
eps = ["VLASS3.1/", "VLASS3.2/"]

#######################################

base = "https://vlass-dl.nrao.edu/vlass/quicklook/"
root = "/lustre/aoc/observers/nm-15373/ray/downloaded_vlass_fits"
outfile = "VLASS_image_metadata_2026-04-28.csv"
timeout = 30

outdir = os.path.join(root, epname)
os.makedirs(outdir, exist_ok=True)

cols = [
    "Imagename", "Epoch", "Tile", "Phasecenter", "Version", "Obs-time",
    "central_ra", "central_dec", "ra_min", "ra_max", "dec_min", "dec_max",
    "bmaj", "bmin", "bpa"
]

done = set()

if os.path.isfile(outfile):
    with open(outfile, "r", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if row.get("Imagename"):
                done.add(row["Imagename"])

if not os.path.isfile(outfile):
    with open(outfile, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()

def write_row(fits_path, fname, tile):
    h = fits.getheader(fits_path)
    wcs = WCS(h)

    m = re.match(r"(VLASS\d\.\d)\.ql\.(T\d+t\d+)\.(J[+-]?\d+[+-]\d+)\..*?\.(v\d)\.", fname)

    if m:
        epoch = m.group(1)
        tile_name = m.group(2)
        phase = m.group(3)
        version = m.group(4)
    else:
        parts = fname.split(".")
        epoch = parts[0] if len(parts) > 0 else ""
        tile_name = tile.replace("/", "")
        phase = parts[3] if len(parts) > 3 else ""
        version = ""
        for p in parts:
            if re.fullmatch(r"v\d", p):
                version = p

    nax1 = int(h.get("NAXIS1", 0))
    nax2 = int(h.get("NAXIS2", 0))

    cx = (nax1 + 1) / 2
    cy = (nax2 + 1) / 2

    try:
        cen = wcs.pixel_to_world_values(cx, cy, 0, 0)
        central_ra = float(cen[0])
        central_dec = float(cen[1])
    except Exception:
        central_ra = float(h.get("CRVAL1", np.nan))
        central_dec = float(h.get("CRVAL2", np.nan))

    corners = [
        (1, 1, 0, 0),
        (nax1, 1, 0, 0),
        (1, nax2, 0, 0),
        (nax1, nax2, 0, 0),
    ]

    ras = []
    decs = []

    for c in corners:
        try:
            x = wcs.pixel_to_world_values(*c)
            ras.append(float(x[0]) % 360.0)
            decs.append(float(x[1]))
        except Exception:
            pass

    if len(ras) > 0:
        if max(ras) - min(ras) > 180:
            ras2 = [r - 360 if r > 180 else r for r in ras]
            ra_min = min(ras2) % 360
            ra_max = max(ras2) % 360
        else:
            ra_min = min(ras)
            ra_max = max(ras)
        dec_min = min(decs)
        dec_max = max(decs)
    else:
        ra_min = np.nan
        ra_max = np.nan
        dec_min = np.nan
        dec_max = np.nan

    row = {
        "Imagename": fname,
        "Epoch": epoch,
        "Tile": tile_name,
        "Phasecenter": phase,
        "Version": version,
        "Obs-time": h.get("DATE-OBS", ""),
        "central_ra": central_ra,
        "central_dec": central_dec,
        "ra_min": ra_min,
        "ra_max": ra_max,
        "dec_min": dec_min,
        "dec_max": dec_max,
        "bmaj": h.get("BMAJ", np.nan),
        "bmin": h.get("BMIN", np.nan),
        "bpa": h.get("BPA", np.nan),
    }

    with open(outfile, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writerow(row)

for ep in eps:
    ep_url = urljoin(base, ep)

    print()
    print("epoch:", ep, flush=True)

    try:
        r = requests.get(ep_url, timeout=timeout)
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print("epoch fail:", ep_url, e, flush=True)
        continue

    tiles = []
    for a in soup.find_all("a"):
        h = a.get("href")
        if h is not None and h.startswith("T") and h.endswith("/"):
            tiles.append(h)

    print("tiles:", len(tiles), flush=True)

    for ti, tile in enumerate(tiles, start=1):
        tile_url = urljoin(ep_url, tile)

        try:
            r = requests.get(tile_url, timeout=timeout)
            soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print("tile fail:", tile_url, e, flush=True)
            continue

        subs = []
        for a in soup.find_all("a"):
            h = a.get("href")
            if h is not None and h.startswith("VLASS") and h.endswith("/"):
                subs.append(h)

        print(f"{epname} {ti}/{len(tiles)} {tile} subfolders: {len(subs)}", flush=True)

        for sub in subs:
            sub_url = urljoin(tile_url, sub)

            try:
                r = requests.get(sub_url, timeout=timeout)
                soup = BeautifulSoup(r.text, "html.parser")
            except Exception as e:
                print("subfolder fail:", sub_url, e, flush=True)
                continue

            for a in soup.find_all("a"):
                fname = a.get("href")

                if fname is None:
                    continue
                if not fname.endswith(".I.iter1.image.pbcor.tt0.subim.fits"):
                    continue
                if fname in done:
                    print("skip metadata:", fname, flush=True)
                    continue

                local = os.path.join(outdir, fname)
                url = urljoin(sub_url, fname)

                if not os.path.isfile(local):
                    try:
                        print("download:", fname, flush=True)
                        tmpfile = local + ".tmp"
                        wget.download(url, out=tmpfile)
                        print()
                        os.rename(tmpfile, local)
                    except Exception as e:
                        print("download fail:", url, e, flush=True)
                        try:
                            if os.path.isfile(tmpfile):
                                os.remove(tmpfile)
                        except Exception:
                            pass
                        continue

                try:
                    write_row(local, fname, tile)
                    done.add(fname)
                    print("added metadata:", fname, flush=True)
                except Exception as e:
                    print("metadata fail:", fname, e, flush=True)

print()
print("done", epname)
