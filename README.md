# Cobalt-Client
Texture Pack for Minecraft bedrock edition

## Cosmetics

The Cosmetics tab of the mod menu is generated from `tools/cosmetics.json`.

To add a cape:

1. Put the 64x32 cape texture into `.Cobalt/textures/cosmetics/capes/<id>.png`.
2. Add `{ "id": "<id>", "name": "<Display Name>" }` to the `items` of the `cape` category in `tools/cosmetics.json`.
3. Run `python tools/build_cosmetics.py`.

The script rewrites `.Cobalt/ui/cosmetics/generated.json`, `render_controllers/cobalt_cosmetics.render_controllers.json` and the cosmetic entries of `entity/player.entity.json`. Do not edit those by hand. The look of the tiles lives in `.Cobalt/ui/cosmetics/template.json`.

A new category (hats, wings, ...) is another entry in `categories` with its own geometry, material, texture folder and preview crop. How the menu reaches the render controllers is explained at the top of `tools/build_cosmetics.py`. Note the cost described there: the number of hidden paper dolls grows quickly with long lists and with every extra category.

`"debug": true` in `tools/cosmetics.json` shows the otherwise off-screen bridge paper dolls at the top left of the HUD: with cape number k equipped, k dolls stand side by side. Set it to `false` and rerun the script for normal use.

### Credits

MINECON cape textures come from the Custom Capes pack made by Xatalyst, capes provided by BionicBens.
