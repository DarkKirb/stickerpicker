# maunium-stickerpicker - A fast and simple Matrix sticker picker widget.
# Copyright (C) 2020 Tulir Asokan
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from typing import Dict, Optional, Tuple
import argparse
import asyncio
import os.path
import json
import re

from telethon import TelegramClient
from telethon.tl.functions.messages import GetAllStickersRequest, GetStickerSetRequest
from telethon.tl.types.messages import AllStickers
from telethon.tl.types import InputStickerSetShortName, InputStickerSetID, Document, DocumentAttributeSticker
from telethon.tl.types.messages import StickerSet as StickerSetFull

from .lib import matrix, util


async def reupload_document(client: TelegramClient, document: Document) -> Optional[Tuple[matrix.StickerInfo, bytes]]:
    print(f"Reuploading {document.id}", end="", flush=True)
    data = await client.download_media(document, file=bytes)
    print(".", end="", flush=True)
    try:
        data, width, height = util.convert_image(data)
    except Exception as e:
        return None
    print(".", end="", flush=True)
    while True:
        try:
            mxc = await matrix.upload(data, "image/webp", f"{document.id}.webp")
            break
        except Exception:
            print("E", end='', flush=True)
    print(".", flush=True)
    return util.make_sticker(mxc, width, height, len(data)), data


def add_meta(i: int, document: Document, info: matrix.StickerInfo, pack: StickerSetFull) -> None:
    for attr in document.attributes:
        if isinstance(attr, DocumentAttributeSticker):
            info["body"] = f"{i:03d} {attr.alt}"
    info["id"] = f"tg-{document.id}"
    info["net.maunium.telegram.sticker"] = {
        "pack": {
            "id": str(pack.set.id),
            "short_name": pack.set.short_name,
        },
        "id": str(document.id),
        "emoticons": [],
    }


async def reupload_pack(client: TelegramClient, pack: StickerSetFull, output_dir: str, sem: asyncio.Semaphore) -> None:
    pack_path = os.path.join(output_dir, f"{pack.set.short_name}.json")
    try:
        os.mkdir(os.path.dirname(pack_path))
    except FileExistsError:
        pass

    print(f"Reuploading {pack.set.title} with {pack.set.count} stickers "
          f"and writing output to {pack_path}")

    already_uploaded = {}
    try:
        with util.open_utf8(pack_path) as pack_file:
            existing_pack = json.load(pack_file)
            already_uploaded = {int(sticker["net.maunium.telegram.sticker"]["id"]): sticker
                                for sticker in existing_pack["stickers"]}
            print(f"Found {len(already_uploaded)} already reuploaded stickers")
    except FileNotFoundError:
        pass

    stickers_data: Dict[str, bytes] = {}
    reuploaded_documents: Dict[int, matrix.StickerInfo] = {}
    futs = []

    async def upload_document(i, document):
        async with sem:
            try:
                # Ensure that document still exists
                if (data := await matrix.download(already_uploaded[document.id]["url"])) is not None:
                    reuploaded_documents[document.id] = already_uploaded[document.id]
                    print(f"Skipped reuploading {document.id}")
                else:
                    res = await reupload_document(client, document)
                    if res is not None:
                        reuploaded_documents[document.id], data = await reupload_document(client, document)
                    else:
                        return
            except KeyError:
                res = await reupload_document(client, document)
                if res is not None:
                    reuploaded_documents[document.id], data = await reupload_document(client, document)
                else:
                    return
            # Always ensure the body and telegram metadata is correct
            add_meta(i, document, reuploaded_documents[document.id], pack)
            stickers_data[reuploaded_documents[document.id]["url"]] = data

    for i, document in enumerate(pack.documents):
        futs.append(upload_document(i, document))

    await asyncio.gather(*futs)

    for sticker in pack.packs:
        if not sticker.emoticon:
            continue
        for document_id in sticker.documents:
            if document_id not in reuploaded_documents:
                continue
            doc = reuploaded_documents[document_id]
            # If there was no sticker metadata, use the first emoji we find
            if doc["body"] == "":
                doc["body"] = sticker.emoticon
            doc["net.maunium.telegram.sticker"]["emoticons"].append(sticker.emoticon)

    with util.open_utf8(pack_path, "w") as pack_file:
        stickers = []
        for id in sorted(reuploaded_documents.keys()):
            stickers.append(reuploaded_documents[id])
        json.dump({
            "title": pack.set.title,
            "id": f"tg-{pack.set.id}",
            "net.maunium.telegram.pack": {
                "short_name": pack.set.short_name,
                "hash": str(pack.set.hash),
            },
            "stickers": stickers,
        }, pack_file, ensure_ascii=False, indent=4)
    print(f"Saved {pack.set.title} as {pack.set.short_name}.json")

    util.add_thumbnails(list(reuploaded_documents.values()), stickers_data, output_dir)
    util.add_to_index(os.path.basename(pack_path), output_dir)


pack_url_regex = re.compile(r"^(?:(?:https?://)?(?:t|telegram)\.(?:me|dog)/addstickers/)?"
                            r"([A-Za-z0-9-_]+)"
                            r"(?:\.json)?$")
sticker_set_id_regex = re.compile(r"(\d+),(-?\d+)")

parser = argparse.ArgumentParser()

parser.add_argument("--list", help="List your saved sticker packs", action="store_true")
parser.add_argument("--session", help="Telethon session file name", default="sticker-import")
parser.add_argument("--config",
                    help="Path to JSON file with Matrix homeserver and access_token",
                    type=str, default="config.json")
parser.add_argument("--output-dir", help="Directory to write packs to", default="web/packs/",
                    type=str)
parser.add_argument("pack", help="Sticker pack URLs to import", action="append", nargs="*")


async def main(args: argparse.Namespace) -> None:
    await matrix.load_config(args.config)
    client = TelegramClient(args.session, 298751, "cb676d6bae20553c9996996a8f52b4d7")
    await client.start()

    if args.list:
        stickers: AllStickers = await client(GetAllStickersRequest(hash=0))
        index = 1
        width = len(str(len(stickers.sets)))
        print("Your saved sticker packs:")
        for saved_pack in stickers.sets:
            print(f"{index:>{width}}. {saved_pack.title} "
                  f"(t.me/addstickers/{saved_pack.short_name})")
            index += 1
    elif args.pack[0]:
        input_packs = []
        for pack_url in args.pack[0]:
            if match := pack_url_regex.match(pack_url):
                input_packs.append(InputStickerSetShortName(short_name=match.group(1)))
            elif match := sticker_set_id_regex.match(pack_url):
                input_packs.append(InputStickerSetID(id=int(match.group(1)), access_hash=int(match.group(2))))
            else:
                print(f"invalid url: {pack_url}")
                return
        sem = asyncio.Semaphore(16)
        async def do_pack(input_pack):
            async with sem:
                try:
                    pack: StickerSetFull = await client(GetStickerSetRequest(input_pack, hash=0))
                except Exception as e:
                    print(e)
                    return
            await reupload_pack(client, pack, args.output_dir, sem)

        futs = []
        for input_pack in input_packs:
            futs.append(do_pack(input_pack))
        await asyncio.gather(*futs)
    else:
        parser.print_help()

    await client.disconnect()


def cmd() -> None:
    asyncio.run(main(parser.parse_args()))


if __name__ == "__main__":
    cmd()
