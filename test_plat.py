"""Self-check for the name rules Windows depends on: python test_plat.py"""
import sys
sys.path.insert(0, "pipeline")
import plat
n = plat.safe_name
assert n("ويحذركم الله نفسه. ｜ بمسجد قباء ｜ للشيخ.") == "ويحذركم الله نفسه. ｜ بمسجد قباء ｜ للشيخ"  # a trailing dot breaks Windows folders
assert n('a:b*c?"d<e>f|g/h\\i') == "a b c  d e f g h i"
assert n("...") == "video" and len(n("ا" * 300)) == 80
assert plat.url("/tmp/a b.png").startswith("file:///") and " " not in plat.url("/tmp/a b.png")
print("ok")
