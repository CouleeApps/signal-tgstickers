import requests
from io import BytesIO
from PIL import Image
import os
from configparser import ConfigParser
from moviepy.editor import VideoFileClip
import glob
import hashlib
import tempfile

# read the configuration file
config = ConfigParser()
config.read('config.ini')

# read the bot token and output directory from the configuration file
bot_token = config['CONFIG']['bot_token']
base_output_dir = config['CONFIG']['output_dir']

# define the desired maximum size for the images (shouldn't need to change this if you're using for signal)
max_size = (512, 512)

# define the desired output formats - png, webp, etc. 
# if using multiple, separate like ['webp', 'png']
output_formats = ['webp']

pack_names = []

while True:
    # prompt the user for the sticker pack name and strip the full url if it exists
    sticker_pack_name = input('Enter the URL/name of the Telegram sticker pack: ')
    if sticker_pack_name.strip() == "":
        break
    sticker_pack_name = sticker_pack_name.replace('https://t.me/addstickers/', '')
    pack_names.append(sticker_pack_name)


for sticker_pack_name in pack_names:
    # prompt the user to create the output directory if it doesn't exist
    output_dir = os.path.join(base_output_dir, sticker_pack_name)
    if not os.path.exists(output_dir):
        print(f'The directory {output_dir} does not exist.')
        # create_dir = input(f'Do you want to create the directory {output_dir}? (y/n) ')
        # if create_dir.lower() == 'y':
        os.makedirs(output_dir)
        # else:
        #     print('Aborting conversion...')
        #     exit()

    # make a request to the telegram bot api to get the sticker pack
    response = requests.get(f'https://api.telegram.org/bot{bot_token}/getStickerSet?name={sticker_pack_name}')

    if response.status_code != 200:
        print(f'Got non-200 status code for {sticker_pack_name}')
        continue

    existing_files = {}
    for exist in glob.glob(os.path.join(output_dir, '*')):
        if not os.path.isfile(exist):
            continue
        with open(exist, 'rb') as f:
            h = hashlib.sha256()
            h.update(f.read())
            if h.hexdigest() not in existing_files:
                existing_files[h.hexdigest()] = []
            existing_files[h.hexdigest()].append(exist)

    # parse the response to get the list of stickers
    stickers = response.json()['result']['stickers']

    # loop through each sticker and convert it
    print(f'Converting {sticker_pack_name} {len(stickers)} stickers...')
    for i, sticker in enumerate(stickers):
        # download the image
        file_id = sticker['file_id']
        response = requests.get(f'https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}')
        file_path = response.json()['result']['file_path']
        response = requests.get(f'https://api.telegram.org/file/bot{bot_token}/{file_path}')
        
        if 'is_video' in sticker and sticker['is_video']:
            # extract frames and frame rate from the animated WebM
            with tempfile.NamedTemporaryFile(suffix='.webm') as f:
                f.write(response.content)
                f.seek(0)
                video_clip = VideoFileClip(f.name)
                frames = video_clip.iter_frames()
                fps = int(video_clip.fps)

        elif 'is_animated' in sticker and sticker['is_animated']:
            print('Sticker Pack appears to be using the .tgs format, support for this is currently in progress.')
            exit()

            # create the APNG from the frames
            apng_frames = [Image.fromarray(frame) for frame in frames]
            output_path = os.path.join(output_dir, f'{i+1}_{sticker["emoji"]}_{sticker["file_unique_id"]}.apng')
            print(f'Converting {sticker["file_unique_id"]} to APNG...')
            apng_duration = int(1000 / fps)  # duration of each frame in ms
            apng_frames[0].save(output_path, save_all=True, append_images=apng_frames[1:], duration=apng_duration, loop=0)

        else:
            # convert the image to PIL format
            image = Image.open(BytesIO(response.content))
        
            # resize the image if necessary
            if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                print(f'Resizing {sticker["file_unique_id"]}...')
                image.thumbnail(max_size)
            
            # convert the image to the desired formats
            for format in output_formats:
                output_path = os.path.join(output_dir, f'{i+1}_{sticker["emoji"]}_{sticker["file_unique_id"]}.{format}')
                print(f'Converting {sticker_pack_name}/{i} {sticker["emoji"]} ({sticker["file_unique_id"]}) to {format}...')
                image.save(output_path, format=format)

                # see if it's a duplicate
                with open(output_path, 'rb') as f:
                    h = hashlib.sha256()
                    h.update(f.read())
                    digest = h.hexdigest()
                # delete duplicates (have 2 or more of same file)
                if digest not in existing_files:
                    existing_files[digest] = []
                if output_path not in existing_files[digest]:
                    existing_files[digest].append(output_path)
                
                for extra in existing_files[digest]:
                    if extra != output_path:
                        os.unlink(extra)
                        print(f'... found a duplicate: {extra}, deleting...')


    print('Conversion complete!')