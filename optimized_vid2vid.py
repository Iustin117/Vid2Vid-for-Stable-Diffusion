from contextlib import contextmanager, nullcontext
from pytorch_lightning import seed_everything
from ldm.util import instantiate_from_config
from torchvision.utils import make_grid
from einops import rearrange, repeat
from operator import length_hint
from omegaconf import OmegaConf
from tqdm import tqdm, trange
from genericpath import isdir
from itertools import islice
from einops import rearrange
from tokenize import Double
from torch import autocast
from PIL import Image
import numpy as np
import argparse
import random
import torch
import time
import glob
import copy
import cv2
import sys
import os
import re


def chunk(it, size):
    it = iter(it)
    return iter(lambda: tuple(islice(it, size)), ())


def load_model_from_config(ckpt, verbose=False):
    print(f"Loading model from {ckpt}")
    pl_sd = torch.load(ckpt, map_location="cpu")
    if "global_step" in pl_sd:
        print(f"Global Step: {pl_sd['global_step']}")
    sd = pl_sd["state_dict"]
    return sd


def load_img(path, h0, w0):

    image = Image.open(path).convert("RGB")
    w, h = image.size

    print(f"loaded input image of size ({w}, {h}) from {path}")
    if(h0 is not None and w0 is not None):
        h, w = h0, w0

    # resize to integer multiple of 64
    w, h = map(lambda x: x - x % 64, (w, h))

    print(f"New image size ({w}, {h})")
    image = image.resize((w, h), resample=Image.LANCZOS)
    image = np.array(image).astype(np.float32) / 255.0
    image = image[None].transpose(0, 3, 1, 2)
    image = torch.from_numpy(image)
    return 2.*image - 1.


config = r"optimizedSD\v1-inference.yaml"
ckpt = r"model 1.3.ckpt"
device = "cuda"

parser = argparse.ArgumentParser()

parser.add_argument(
    "--prompt",
    type=str,
    nargs="?",
    default="a painting of a virus monster playing guitar",
    help="the prompt to render"
)
parser.add_argument(
    "--outdir",
    type=str,
    nargs="?",
    help="dir to write results to",
    default="outputs/img2img-samples"
)

parser.add_argument(
    "--skip_grid",
    action='store_true',
    help="do not save a grid, only individual samples. Helpful when evaluating lots of samples",
)
parser.add_argument(
    "--skip_save",
    action='store_true',
    help="do not save individual samples. For speed measurements.",
)
parser.add_argument(
    "--ddim_steps",
    type=int,
    default=50,
    help="number of ddim sampling steps",
)

parser.add_argument(
    "--ddim_eta",
    type=float,
    default=0.0,
    help="ddim eta (eta=0.0 corresponds to deterministic sampling",
)
parser.add_argument(
    "--n_iter",
    type=int,
    default=1,
    help="sample this often",
)
parser.add_argument(
    "--H",
    type=int,
    default=None,
    help="image height, in pixel space",
)
parser.add_argument(
    "--W",
    type=int,
    default=None,
    help="image width, in pixel space",
)
parser.add_argument(
    "--strength",
    type=float,
    default=0.75,
    help="strength for noising/unnoising. 1.0 corresponds to full destruction of information in init image",
)
parser.add_argument(
    "--C",
    type=int,
    default=4,
    help="latent channels",
)
parser.add_argument(
    "--f",
    type=int,
    default=8,
    help="downsampling factor",
)
parser.add_argument(
    "--n_samples",
    type=int,
    default=1,
    help="how many samples to produce for each given prompt. A.k.a. batch size",
)
parser.add_argument(
    "--n_rows",
    type=int,
    default=0,
    help="rows in the grid (default: n_samples)",
)
parser.add_argument(
    "--scale",
    type=float,
    default=7.5,
    help="unconditional guidance scale: eps = eps(x, empty) + scale * (eps(x, cond) - eps(x, empty))",
)
parser.add_argument(
    "--from-file",
    type=str,
    help="if specified, load prompts from this file",
)
parser.add_argument(
    "--seed",
    type=int,
    default=42,
    help="the seed (for reproducible sampling)",
)
parser.add_argument(
    "--small_batch",
    action='store_true',
    help="Reduce inference time when generate a smaller batch of images",
)
parser.add_argument(
    "--precision",
    type=str,
    help="evaluate at this precision",
    choices=["full", "autocast"],
    default="autocast"
)

# New arguments:
parser.add_argument(
    "--vid_file",
    type=str,
    help=" point to the video file"
)


opt = parser.parse_args()

tic = time.time()
os.makedirs(opt.outdir, exist_ok=True)
outpath = opt.outdir

sample_path = os.path.join(outpath, "_".join(opt.prompt.split())[:255])
os.makedirs(sample_path, exist_ok=True)
base_count = len(os.listdir(sample_path))


# Vid to img
videoFileName = opt.vid_file
vidcap = cv2.VideoCapture(videoFileName)
success, image = vidcap.read()
count = 0

path_to_frames = os.path.join(sample_path, "frames")


if not os.path.isdir(path_to_frames):
    os.makedirs(path_to_frames, exist_ok=True)
    while success:
        cv2.imwrite(path_to_frames + "/%d.png" %
                    count, image)     # save frame as JPEG file
        success, image = vidcap.read()
        count += 1

initial_image_folder = path_to_frames
initial_images = [img for img in os.listdir(
    initial_image_folder) if img.endswith(".png")]
initial_images = sorted(
    initial_images, key=lambda x: int(os.path.splitext(x)[0]))
grid_count = len(os.listdir(outpath)) - 1
seed_everything(opt.seed)


sd = load_model_from_config(f"{ckpt}")
li = []
lo = []

for key, value in sd.items():
    sp = key.split('.')
    if(sp[0]) == 'model':
        if('input_blocks' in sp):
            li.append(key)
        elif('middle_block' in sp):
            li.append(key)
        elif('time_embed' in sp):
            li.append(key)
        else:
            lo.append(key)
for key in li:
    sd['model1.' + key[6:]] = sd.pop(key)
for key in lo:
    sd['model2.' + key[6:]] = sd.pop(key)

config = OmegaConf.load(f"{config}")
config.modelUNet.params.ddim_steps = opt.ddim_steps

if opt.small_batch:
    config.modelUNet.params.small_batch = True
else:
    config.modelUNet.params.small_batch = False

model = instantiate_from_config(config.modelUNet)
_, _ = model.load_state_dict(sd, strict=False)
model.eval()

modelCS = instantiate_from_config(config.modelCondStage)
_, _ = modelCS.load_state_dict(sd, strict=False)
modelCS.eval()

modelFS = instantiate_from_config(config.modelFirstStage)
_, _ = modelFS.load_state_dict(sd, strict=False)
modelFS.eval()

for png in initial_images:
    path_to_frame = os.path.join(path_to_frames, png)
    init_image = load_img(path_to_frame, opt.H, opt.W).to(device)

    if opt.precision == "autocast":
        model.half()
        modelCS.half()
        modelFS.half()
        init_image = init_image.half()

    batch_size = opt.n_samples
    n_rows = opt.n_rows if opt.n_rows > 0 else batch_size
    if not opt.from_file:
        prompt = opt.prompt
        assert prompt is not None
        data = [batch_size * [prompt]]

    else:
        print(f"reading prompts from {opt.from_file}")
        with open(opt.from_file, "r") as f:
            data = f.read().splitlines()
            data = list(chunk(data, batch_size))

    modelFS.to(device)

    assert os.path.isfile(path_to_frame)
    # init_image = load_img(opt.init_img, opt.H, opt.W).to(device)
    init_image = repeat(init_image, '1 ... -> b ...', b=batch_size)
    init_latent = modelFS.get_first_stage_encoding(
        modelFS.encode_first_stage(init_image))  # move to latent space

    mem = torch.cuda.memory_allocated()/1e6
    modelFS.to("cpu")
    while(torch.cuda.memory_allocated()/1e6 >= mem):
        time.sleep(1)

    assert 0. <= opt.strength <= 1., 'can only work with strength in [0.0, 1.0]'
    t_enc = int(opt.strength * opt.ddim_steps)
    print(f"target t_enc is {t_enc} steps")

    precision_scope = autocast if opt.precision == "autocast" else nullcontext
    with torch.no_grad():

        all_samples = list()
        for n in trange(opt.n_iter, desc="Sampling"):
            for prompts in tqdm(data, desc="data"):
                with precision_scope("cuda"):
                    modelCS.to(device)
                    uc = None
                    if opt.scale != 1.0:
                        uc = modelCS.get_learned_conditioning(
                            batch_size * [""])
                    if isinstance(prompts, tuple):
                        prompts = list(prompts)

                    c = modelCS.get_learned_conditioning(prompts)
                    mem = torch.cuda.memory_allocated()/1e6
                    modelCS.to("cpu")
                    while(torch.cuda.memory_allocated()/1e6 >= mem):
                        time.sleep(1)

                    # encode (scaled latent)
                    z_enc = model.stochastic_encode(
                        init_latent, torch.tensor([t_enc]*batch_size).to(device))
                    # decode it
                    samples_ddim = model.decode(z_enc, c, t_enc, unconditional_guidance_scale=opt.scale,
                                                unconditional_conditioning=uc,)

                    modelFS.to(device)
                    print("saving images")
                    for i in range(batch_size):

                        x_samples_ddim = modelFS.decode_first_stage(
                            samples_ddim[i].unsqueeze(0))
                        x_sample = torch.clamp(
                            (x_samples_ddim + 1.0) / 2.0, min=0.0, max=1.0)
                    # for x_sample in x_samples_ddim:
                        x_sample = 255. * \
                            rearrange(
                                x_sample[0].cpu().numpy(), 'c h w -> h w c')
                        Image.fromarray(x_sample.astype(np.uint8)).save(
                            os.path.join(sample_path, f"{base_count:05}.png"))
                        os.remove(path_to_frame)
                        base_count += 1

                    mem = torch.cuda.memory_allocated()/1e6
                    modelFS.to("cpu")
                    while(torch.cuda.memory_allocated()/1e6 >= mem):
                        time.sleep(1)

                    # if not opt.skip_grid:
                    #     all_samples.append(x_samples_ddim)
                    del samples_ddim
                    print("memory_final = ", torch.cuda.memory_allocated()/1e6)

            # if not skip_grid:
            #     # additionally, save as grid
            #     grid = torch.stack(all_samples, 0)
            #     grid = rearrange(grid, 'n b c h w -> (n b) c h w')
            #     grid = make_grid(grid, nrow=n_rows)

            #     # to image
            #     grid = 255. * rearrange(grid, 'c h w -> h w c').cpu().numpy()
            #     Image.fromarray(grid.astype(np.uint8)).save(os.path.join(outpath, f'grid-{grid_count:04}.png'))
            #     grid_count += 1

    toc = time.time()

    time_taken = (toc-tic)/60.0

    print(
        ("Your samples are ready in {0:.2f} minutes and waiting for you here \n" + sample_path).format(time_taken))
