import json

counter = 0

packs = json.load(open("../web/packs/index.json", "r"))

def save_if_needed(id, pack, images, force = False):
    result = {
        "images": images,
        "pack": pack
    }
    value = json.dumps(result)
    if force or (len(value) > 60000):
        global counter
        with open(f"{id}-{counter}.json", "w") as f:
            print(f"Flushing: {id}-{counter}.json")
            f.write(value)
        counter += 1
        return True
    return False

images = {}

def process_image(img):
    img["info"]["net.maunium.telegram.sticker"] = img["net.maunium.telegram.sticker"]
    print(img)
    image = {
        "url": img["url"],
        "body": img["body"],
        "info": img["info"]
    }
    short_name = img["net.maunium.telegram.sticker"]["pack"]["short_name"]
    for emoticon in [img["net.maunium.telegram.sticker"]["emoticons"][0]]:
        emoticon += f" ({short_name})"
        yield (emoticon, image)

def process_images(stickers):
    for img in stickers:
        yield from process_image(img)

for pack in packs["packs"]:
    info = json.load(open(f"../web/packs/{pack}", "r"))
    try:
        pack = {
            "display_name": info["title"],
            "avatar_url": info["stickers"][0]["url"],
            "usage": ["sticker", "emoji"],
            "attribution": f"https://t.me/addstickers/{info['net.maunium.telegram.pack']['short_name']}"
        }
    except:
        continue
    images = {}
    counter = 0
    sticker_ids = {}
    for (i, (name2, imgInfo)) in enumerate(process_images(info["stickers"])):
        name = f"{info['net.maunium.telegram.pack']['short_name']}{i:03d}{name2}"
        images[name] = imgInfo
        if save_if_needed(info["id"], pack, images):
            images = {}
    save_if_needed(info["id"], pack, images, force=True)
