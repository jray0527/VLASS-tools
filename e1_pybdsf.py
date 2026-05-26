import os
import glob
import bdsf
from astropy.table import Table, vstack

ep = "E1"
fitsdir = f"/lustre/aoc/observers/nm-15373/ray/downloaded_vlass_fits/{ep}"
ncore = 5

outdir = f"{ep}_pybdsf_parts"
outcat = f"{ep}_raw_pybdsf.fits"
failfile = f"{ep}_pybdsf_failed.txt"

os.makedirs(outdir, exist_ok=True)

files = sorted(glob.glob(f"{fitsdir}/**/*tt0.subim.fits", recursive=True))

print(f"{ep}: found {len(files)} files", flush=True)

for f in files:
    base = os.path.basename(f).replace(".fits", ".pybdsf.fits")
    catfile = os.path.join(outdir, base)

    if os.path.exists(catfile):
        try:
            old = Table.read(catfile)
            if len(old) > 0:
                print(f"skip {base}", flush=True)
                continue
            else:
                print(f"redo empty {base}", flush=True)
        except Exception:
            print(f"redo bad {base}", flush=True)

        try:
            os.remove(catfile)
        except Exception:
            pass

    print(f"running {base}", flush=True)

    try:
        img = bdsf.process_image(
            f,
            thresh_isl=3.0,
            thresh_pix=5.0,
            rms_box=(100, 30),
            adaptive_rms_box=True,
            atrous_do=False,
            ncores=ncore,
            quiet=True
        )

        img.write_catalog(
            outfile=catfile,
            catalog_type="srl",
            format="fits",
            clobber=True
        )

        t = Table.read(catfile)
        t["image_file"] = os.path.basename(f)
        t["image_path"] = f
        t["epoch"] = ep
        t.write(catfile, overwrite=True)

        print(f"added {len(t)} sources", flush=True)

    except Exception as e:
        print(f"failed {base}", flush=True)
        print(e, flush=True)
        with open(failfile, "a") as x:
            x.write(f"{f}\n{e}\n\n")

tabs = []

for c in sorted(glob.glob(f"{outdir}/*.fits")):
    try:
        tabs.append(Table.read(c))
    except Exception as e:
        print(f"could not read {c}", flush=True)
        print(e, flush=True)

if len(tabs) > 0:
    cat = vstack(tabs, join_type="outer")
    cat.write(outcat, overwrite=True)
    print(f"wrote {outcat} with {len(cat)} rows", flush=True)
else:
    print("no catalogs made", flush=True)
