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

sticker_ids = {}
images = {}

def process_image(img):
    img["info"]["net.maunium.telegram.sticker"] = img["net.maunium.telegram.sticker"]
    image = {
        "url": img["url"],
        "body": img["body"],
        "info": img["info"]
    }
    short_name = img["net.maunium.telegram.sticker"]["pack"]["short_name"]
    for emoticon in [img["net.maunium.telegram.sticker"]["emoticons"][0]]:
        emoticon += f" ({short_name})"
        if emoticon in sticker_ids:
            yield (emoticon + str(sticker_ids[emoticon]), image)
            sticker_ids[emoticon] += 1
        else:
            yield (emoticon, image)
            sticker_ids[emoticon] = 1

def process_images(stickers):
    for img in stickers:
        yield from process_image(img)

for pack in packs["packs"]:
    info = json.load(open(f"../web/packs/{pack}", "r"))
    pack = {
        "display_name": info["title"],
        "avatar_url": info["stickers"][0]["url"],
        "usage": ["sticker", "emoji"],
        "attribution": f"https://t.me/addstickers/{info['net.maunium.telegram.pack']['short_name']}"
    }
    images = {}
    counter = 0
    sticker_ids = {}
    for (name, imgInfo) in process_images(info["stickers"]):
        images[name] = imgInfo
        if save_if_needed(info["id"], pack, images):
            images = {}
    save_if_needed(info["id"], pack, images, force=True)
