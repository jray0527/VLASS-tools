#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import os
import csv
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from astropy.io import fits
from astropy.wcs import WCS
import numpy as np

top_url = "https://vlass-dl.nrao.edu/vlass/quicklook/"
epoch_dirs = [
    "VLASS1.1v2/", "VLASS1.2v2/", "VLASS2.1/", "VLASS2.2/",
    "VLASS3.1/", "VLASS3.2/", "VLASS4.1/"
]

fits_pattern = re.compile(r".*\.tt0\.subim\.fits$", re.IGNORECASE)
target_pattern = re.compile(r"[Jj]\d{6}[+-]\d{6}")
version_pattern = re.compile(r"\.v(\d+)\.", re.IGNORECASE)
output_csv = "VLASS_image_metadata_2023-06-05.csv"
outdir = "vlass_fits"


def safe_get(url, stream=False, delay=0.1, retries=8):
    for i in range(retries):
        try:
            resp = requests.get(url, stream=stream, timeout=60)
            if resp.status_code == 429:
                print(f"[ERR] Too many requests, waiting 5 sec...")
                time.sleep(5)
                continue
            resp.raise_for_status()
            time.sleep(delay)
            return resp
        except requests.exceptions.RequestException as e:
            print(f"[RETRY] Attempt {i+1}: {e}")
            time.sleep(5)
    raise RuntimeError(f"Failed request: {url}")


def load_processed(csv_file):
    processed = set()
    if os.path.exists(csv_file):
        with open(csv_file, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get('Imagename', '').strip()
                if name:
                    processed.add(name)
    return processed


def list_tiles(epoch_url):
    print(f"[PARSE] Getting tiles in {epoch_url}")
    resp = safe_get(epoch_url)
    soup = BeautifulSoup(resp.text, 'html.parser')
    return [a['href'] for a in soup.find_all('a', href=True)
            if a['href'].endswith('/') and a['href'].startswith('T')]


def list_targets(tile_url):
    print(f"[PARSE] Getting targets in {tile_url}")
    resp = safe_get(tile_url)
    soup = BeautifulSoup(resp.text, 'html.parser')
    return [a['href'] for a in soup.find_all('a', href=True)
            if a['href'].endswith('/') and a['href'].lower().startswith('vlass')]


def get_bounds(filepath):
    header = fits.getheader(filepath)
    data = fits.getdata(filepath, memmap=False)
    data = np.squeeze(data)
    ny, nx = data.shape[-2], data.shape[-1]

    wcs_full = WCS(header)
    try:
        wcs = wcs_full.celestial
    except Exception:
        wcs = wcs_full

    corners = np.array([
        [0, 0],
        [nx - 1, 0],
        [0, ny - 1],
        [nx - 1, ny - 1]
    ], dtype=float)

    world = wcs.pixel_to_world_values(corners[:, 0], corners[:, 1])
    ra = np.array(world[0], dtype=float) % 360.0
    dec = np.array(world[1], dtype=float)

    return header, ra.min(), ra.max(), dec.min(), dec.max()


def process_target(epoch, tile, target_dir, tile_url, writer, processed):
    target_url = urljoin(tile_url, target_dir)
    print(f"[PARSE] Opening {target_url}")
    resp = safe_get(target_url)
    soup = BeautifulSoup(resp.text, 'html.parser')

    for a in soup.find_all('a', href=True):
        href = a['href']
        if fits_pattern.match(href):
            filename = os.path.basename(href)

            if filename in processed:
                print(f"[SKIP] Already processed {filename}")
                return

            file_url = urljoin(target_url, href)
            os.makedirs(outdir, exist_ok=True)
            filepath = os.path.join(outdir, filename)

            print(f"[GET] {file_url}")
            file_resp = safe_get(file_url, stream=True)

            with open(filepath, 'wb') as out_f:
                for chunk in file_resp.iter_content(chunk_size=8192):
                    out_f.write(chunk)

            try:
                hdr, ra_min, ra_max, dec_min, dec_max = get_bounds(filepath)

                match = target_pattern.search(filename)
                phasecenter = match.group(0) if match else ''

                version_match = version_pattern.search(filename)
                version = f"v{version_match.group(1)}" if version_match else ''

                writer.writerow([
                    filename,
                    epoch.rstrip('/'),
                    tile,
                    phasecenter,
                    version,
                    hdr.get('DATE-OBS', ''),
                    hdr.get('CRVAL1', ''),
                    hdr.get('CRVAL2', ''),
                    ra_min,
                    ra_max,
                    dec_min,
                    dec_max,
                    hdr.get('BMAJ', ''),
                    hdr.get('BMIN', ''),
                    hdr.get('BPA', '')
                ])

                processed.add(filename)
                print(f"[FOUND] {filename} | {epoch} | {tile} | {phasecenter}")

            except Exception as e:
                print(f"[ERROR] Cannot read {filepath}: {e}")

            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)

            return


def main():
    processed = load_processed(output_csv)
    mode = 'a' if os.path.exists(output_csv) else 'w'

    with open(output_csv, mode, newline='') as csvfile:
        writer = csv.writer(csvfile)

        if mode == 'w':
            writer.writerow([
                'Imagename', 'Epoch', 'Tile', 'Phasecenter', 'Version', 'Obs-time',
                'central_ra', 'central_dec', 'ra_min', 'ra_max', 'dec_min', 'dec_max',
                'bmaj', 'bmin', 'bpa'
            ])

        for epoch_dir in epoch_dirs:
            epoch_url = urljoin(top_url, epoch_dir)
            epoch_name = epoch_dir.rstrip('/')

            for tile_dir in list_tiles(epoch_url):
                tile = tile_dir.rstrip('/')
                tile_url = urljoin(epoch_url, tile_dir)

                for target_dir in list_targets(tile_url):
                    process_target(epoch_name, tile, target_dir, tile_url, writer, processed)

    if os.path.isdir(outdir) and not os.listdir(outdir):
        os.rmdir(outdir)

    print(f"[COMPLETE] Updated {output_csv}")


if __name__ == '__main__':
    main()


# In[ ]:




