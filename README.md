# Vid2Vid-for-Stable-Diffusion
How to run:

*  Place the optimized_Vid2Vid.py in the optimizedSD folder [ just for making the bat file work, but you can edit the bat file as well] 
*  Place the img2vid.py andt img2vid.bat in the "output/img2img-samples" folder 
*  Run the optimized_Vid2Vid.py [-h to show all arguments] point to the inital video file [--vid_file] enter a prompt, seed, scale, height and width exactly like in img2img.py, but set the --strength to a low value [0.2, 0.3]
*  Now in the output/img2img-samples you will have a new foler with the name of the prompt, and insid it another folder named frames. Now is the time to stop the script and delet what framse you think are non esensial. By restarting with the same command wthe script will not regenerate the frames you deleted as long as the frames folder is still there.
*  Afther every frame generated the script delets the inital one so that enables us to finish a video in multiple sessions.
*  When the optimized_Vid2Vid.py finished and you have all your generated frames in the folder with the prompt name run the img2vid.py [-h to show all arguments].

