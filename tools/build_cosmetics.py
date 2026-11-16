"""Generates every per-cosmetic file of Cobalt Client from tools/cosmetics.json.

Run from anywhere:  python tools/build_cosmetics.py

To add a cosmetic: drop <id>.png into the category's texture_folder, add
{"id": ..., "name": ...} to tools/cosmetics.json and run this script.

How a cosmetic gets from the menu to the player model
-----------------------------------------------------
Measured in game / read from the game's paper_doll_renderer (1.21.130):
- A binding can show and hide a paper doll (#visible), but bindings into its
  property_bag do not arrive.
- "#disable_head_follow_mouse": true in the property_bag makes the renderer
  set variable.should_look_at_target_ui to 0 on that doll, every frame.
- A paper doll is a dummy player without an entity. It still runs the player
  entity's pre_animation each time it is drawn, with its own variables.
- temp.* variables are shared by everything that renders.
- Doll animations (#animation_to_play) start only once and die when the
  pause screen opens, so nothing here uses them.

A doll therefore carries exactly one bit: "a marked doll was drawn". The
cosmetic is encoded in HOW MANY marked dolls are drawn per frame:
1. Each cosmetic owns a group of off-screen marked dolls that is visible
   while its toggle is on. Item number i of the first category has i dolls;
   later categories count in multiples (see `weight` below), so the total
   decodes like digits of a number.
2. Every marked doll adds 1 to temp.cosmetic_count in pre_animation.
3. The local player's world pass reads the count, clears it and accepts it
   once it has seen the same count twice in a row. Paper dolls and other
   players never read it, so only the local player gets the cosmetic.
4. Each category's render controller takes its digit of the count as texture
   index. Nothing equipped -> no dolls -> the value goes stale -> off.

Cost: item i needs i * weight dolls, so long lists and many categories get
expensive. Six capes need 21 hidden dolls, of which at most 6 are drawn.

"debug": true in cosmetics.json puts the dolls on screen (top left): with
cape number k equipped, k dolls stand side by side.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "tools" / "cosmetics.json"
ENTITY = ROOT / "entity" / "player.entity.json"
UI_OUT = ROOT / ".Cobalt" / "ui" / "cosmetics" / "generated.json"
RC_OUT = ROOT / "render_controllers" / "cobalt_cosmetics.render_controllers.json"

RC_PREFIX = "controller.render.cosmetic."
KEY_PREFIX = "cosmetic_"
VAR_PREFIX = "variable.cosmetic_"
TEMP_PREFIX = "temp.cosmetic_"
COUNT = TEMP_PREFIX + "count"

TILES_PER_ROW = 4
# Seconds the cosmetics stay on after the last count arrived.
STALE_AFTER = 0.3
NONE_PREVIEW = {
    "texture": ".Cobalt/textures/cosmetics/none",
    "uv": [0, 0],
    "uv_size": [40, 40],
    "size": [24, 24],
}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def spacer(name, size):
    return {f"{name}@Cobalt_common.element": {"size": [size, size]}}


def build():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    entity = json.loads(ENTITY.read_text(encoding="utf-8"))
    desc = entity["minecraft:client_entity"]["description"]
    debug = config.get("debug", False)

    # Drop everything a previous run added, so removed cosmetics disappear.
    for section in ("textures", "geometry"):
        desc[section] = {k: v for k, v in desc[section].items() if not k.startswith(KEY_PREFIX)}
    desc["animations"] = {k: v for k, v in desc["animations"].items() if not k.startswith("animation.cobalt.")}
    scripts = desc["scripts"]
    for key in ("initialize", "pre_animation"):
        scripts[key] = [s for s in scripts[key] if not s.startswith((VAR_PREFIX, TEMP_PREFIX))]
    desc["render_controllers"] = [
        rc for rc in desc["render_controllers"]
        if not (isinstance(rc, dict) and next(iter(rc)).startswith(RC_PREFIX))
    ]

    v = VAR_PREFIX
    scripts["initialize"] += [
        f"{v}take = 0.0;", f"{v}prev = 0.0;", f"{v}stable = 0.0;",
        f"{v}time = -100.0;", f"{v}total = 0.0;",
    ]
    # One statement per line; each runs for every player model that is drawn.
    scripts["pre_animation"] += [
        # A marked paper doll adds 1.
        f"{COUNT} = ({COUNT} ?? 0.0) + ((variable.is_paperdoll && (variable.should_look_at_target_ui ?? 1.0) < 0.5) ? 1.0 : 0.0);",
        # Only the local player's world pass reads the count. The ternary
        # keeps query.is_local_player away from dolls, where it errors.
        f"{v}take = (variable.is_paperdoll || query.is_in_ui) ? 0.0 : (query.is_local_player ? ({COUNT} ?? 0.0) : 0.0);",
        f"{COUNT} = {v}take > 0.0 ? 0.0 : ({COUNT} ?? 0.0);",
        # Accept a count once it arrived twice in a row (a frame without a
        # world pass would otherwise show up as a doubled count).
        f"{v}stable = ({v}take > 0.0 && {v}take == {v}prev) ? {v}take : {v}stable;",
        f"{v}prev = {v}take > 0.0 ? {v}take : {v}prev;",
        f"{v}time = {v}take > 0.0 ? query.life_time : {v}time;",
        f"{v}total = (query.life_time - {v}time) < {STALE_AFTER} ? {v}stable : 0.0;",
    ]

    render_controllers = {}
    bridges = []
    page = [spacer("top_spacer", 5)]
    weight = 1  # how many dolls one step of this category's index is worth

    for cat in config["categories"]:
        cid = cat["id"]
        var = f"{VAR_PREFIX}{cid}"
        group = f"Cobalt_cosmetic_{cid}_group"
        preview = cat["preview"]
        folder = cat["texture_folder"].strip("/")
        ids = ["none"] + [item["id"] for item in cat["items"]]
        if len(set(ids)) != len(ids):
            sys.exit(f"{cid}: duplicate or reserved item id (\"none\" is reserved)")
        default_index = ids.index(cat.get("default", "none"))

        def tile(index, item_id, name, texture, uv, uv_size, size):
            return {
                f"{cid}_{item_id}@Cobalt_cosmetics_template.tile": {
                    "$cosmetic_name": name,
                    "$cosmetic_toggle_name": f"Cobalt_cosmetic_{cid}_{item_id}_toggle",
                    "$cosmetic_group": group,
                    "$cosmetic_index": index,
                    "$cosmetic_default_index": default_index,
                    "$cosmetic_preview_texture": texture,
                    "$cosmetic_preview_uv": uv,
                    "$cosmetic_preview_uv_size": uv_size,
                    "$cosmetic_preview_size": size,
                }
            }

        tiles = [tile(0, "none", "None", NONE_PREVIEW["texture"], NONE_PREVIEW["uv"],
                      NONE_PREVIEW["uv_size"], NONE_PREVIEW["size"])]
        # Index 0 is "none"; it reuses the entity's invisible cape texture.
        texture_array = ["Texture.cape"]

        for index, item in enumerate(cat["items"], start=1):
            iid = item["id"]
            texture = f"{folder}/{iid}"
            if not (ROOT / f"{texture}.png").is_file():
                sys.exit(f"{cid}/{iid}: missing texture {texture}.png")
            short = f"{KEY_PREFIX}{cid}_{iid}"

            desc["textures"][short] = texture
            texture_array.append(f"Texture.{short}")
            tiles.append(tile(index, iid, item["name"], texture, preview["uv"],
                              preview["uv_size"], preview["size"]))
            for n in range(index * weight):
                doll = {"$cosmetic_toggle_name": f"Cobalt_cosmetic_{cid}_{iid}_toggle"}
                if debug:
                    doll["$cosmetic_bridge_size"] = [20, 20]
                    doll["$cosmetic_bridge_offset"] = [10 + 22 * (n % 12), 60 + 50 * (n // 12)]
                bridges.append({f"{cid}_{iid}_{n}@Cobalt_cosmetics_template.bridge": doll})

        base = len(cat["items"]) + 1
        desc["geometry"][f"{KEY_PREFIX}{cid}"] = cat["geometry"]
        scripts["initialize"].append(f"{var} = 0.0;")
        # This category's digit of the total.
        scripts["pre_animation"].append(f"{var} = math.mod(math.floor({v}total / {weight}.0), {base}.0);")
        desc["render_controllers"].append({
            f"{RC_PREFIX}{cid}": f"{var} > 0.0 && {cat['render_condition']}"
        })
        render_controllers[f"{RC_PREFIX}{cid}"] = {
            "geometry": f"Geometry.{KEY_PREFIX}{cid}",
            "materials": [{"*": f"Material.{cat['material']}"}],
            "textures": [f"Array.{cid}[{var}]"],
            "arrays": {"textures": {f"Array.{cid}": texture_array}},
        }
        weight *= base

        page.append({f"{cid}_title@Cobalt_cosmetics_template.title": {"$cosmetic_title": cat["title"]}})
        for row_index in range(0, len(tiles), TILES_PER_ROW):
            controls = [spacer("spacer0", 10)]
            for n, t in enumerate(tiles[row_index:row_index + TILES_PER_ROW], start=1):
                controls += [t, spacer(f"spacer{n}", 5)]
            page.append({
                f"{cid}_row{row_index // TILES_PER_ROW}@Cobalt_cosmetics_template.row": {"controls": controls}
            })
            page.append(spacer(f"{cid}_row{row_index // TILES_PER_ROW}_spacer", 5))

    write_json(UI_OUT, {
        "namespace": "Cobalt_cosmetics",
        "content@Cobalt_common.element": {
            "$Cobalt_type": "stack_panel",
            "orientation": "vertical",
            "$Cobalt_anchor": "top_middle",
            "size": ["100%", "100%c + 15px"],
            "controls": page,
        },
        "bridges@Cobalt_common.element": {
            "size": ["100%", "100%"],
            "controls": bridges,
        },
    })
    write_json(RC_OUT, {"format_version": "1.8.0", "render_controllers": render_controllers})
    write_json(ENTITY, entity)
    count = sum(len(cat["items"]) for cat in config["categories"])
    print(f"{count} cosmetics in {len(config['categories'])} categories, {len(bridges)} bridge dolls written.")


if __name__ == "__main__":
    build()
