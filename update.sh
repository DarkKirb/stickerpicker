#!/usr/bin/env nix-shell
#! nix-shell -i bash -p jq
(sticker-import --list | awk '{print $(NF)}' | sed 's/^.//' | sed 's/.$//' | egrep -v '^acks$'; jq -r '.packs[]' web/packs/index.json | sed 's/\.json$//' | sed 's|^|t.me/addstickers/|'; for f in $@; do echo $f; done) | sort -u | xargs sticker-import
