import os
import argparse
import cv2

parser = argparse.ArgumentParser()
parser.add_argument(
    "--vid_name",
    type=str,
    default="video_1",
    help=" the name of the video"
)
parser.add_argument(
    "--fps",
    type=int,
    default=30,
    help=" the video fps, defaulted to 30"
)
parser.add_argument(
    "--img_folder",
    type=str,
    help=" point to the folder containing the generated images/frames"
)

opt = parser.parse_args()

final_image_folder = opt.img_folder
video_name = opt.vid_name + ".mp4"
fps = opt.fps
images = [img for img in os.listdir(
    final_image_folder) if img.endswith(".png")]
frame = cv2.imread(os.path.join(final_image_folder, images[0]))
height, width, layers = frame.shape
video = cv2.VideoWriter(video_name, 0, fps, (width, height))
for image in images:
    video.write(cv2.imread(os.path.join(final_image_folder, image)))
cv2.destroyAllWindows()
video.release()
