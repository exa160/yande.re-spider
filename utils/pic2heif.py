import threading
from pathlib import Path
from time import sleep

import cv2
import numpy as np
import pillow_heif
from PIL import Image
#
# P = r"C:\pyspider\yande.re 1190727 bandages bottomless devil horns iijima_masashi no_bra tail weapon wings.jpg"
# P = r"C:\pyspider\yande.re 1180564 anmi fate_grand_order heels hibino_hibiki katsuragi_chikagi mahou_tsukai_no_hako pantyhose skirt_lift transparent_png.png"
# # P = r"C:\pyspider\yande.re 1128230 ass castlevania castlevania_order_of_ecclesia corset cutesexyrobutts garter garter_belt naked shanoa stockings tattoo thighhighs.png"
# P2 = r"C:\pyspider\yande.re 1190727 bandages bottomless devil horns iijima_masashi no_bra tail weapon wings2.heic"
# P2 = r"C:\pyspider\yande.re 1180564 anmi fate_grand_order heels hibino_hibiki katsuragi_chikagi mahou_tsukai_no_hako pantyhose skirt_lift transparent_png2.heic"
# P3 = r"C:\pyspider\yande.re 1180564 anmi fate_grand_order heels hibino_hibiki katsuragi_chikagi mahou_tsukai_no_hako pantyhose skirt_lift transparent_png3.png"
# # P2 = r"C:\pyspider\yande.re 1128230 ass castlevania castlevania_order_of_ecclesia corset cutesexyrobutts garter garter_belt naked shanoa stockings tattoo thighhighs2.heic"
# A = pillow_heif.open_heif(P2)
# Image.fromarray(np.asarray(A)).save(P3)
#
# print(A.has_alpha)
# with Image.open(P) as f:
#     heif_file = pillow_heif.from_pillow(f)
#     print(f.apply_transparency())
#     print(heif_file.has_alpha)
#     print(heif_file.premultiplied_alpha)
    # heif_file.has_alpha
    # heif_file.save(P2, save_all=True)
# cv_img = cv2.imread(P, cv2.IMREAD_UNCHANGED)
# pillow_heif.encode(
#    mode="RGBA",
#    size=(cv_img.shape[1], cv_img.shape[0]),
#    data=bytes(cv_img),
#    fp=P2,
#    quality=-1)

import os
from PIL import Image
# import pyheif


def dir_work(input_path, output_path):
    input_path = Path(input_path)
    output_path = Path(output_path)
    start_thread = threading.active_count()
    for in_path in input_path.rglob("*"):
        if not in_path.is_file or '.@__thumb' in str(in_path):
            continue
        if in_path.suffix.lower().endswith(('png', 'jpg', 'jpeg', 'bmp')):
            out_path = output_path / in_path.relative_to(input_path).with_suffix('.heic')
            if not out_path.parent.exists():
                out_path.parent.mkdir(parents=True, exist_ok=True)
            t = threading.Thread(target=convert_to_heif, args=(in_path, out_path))
            t.start()
            while threading.active_count() - start_thread > 4:
                sleep(0.2)

    while threading.active_count() > start_thread:
        sleep(2)


def convert_to_heif(in_path: Path, out_path: Path):
    try:
        with Image.open(in_path) as f:
            icc_profile = f.info.get('icc_profile')
            
            heif_file = pillow_heif.from_pillow(f)
            
            # 关键修复：将 ICC 配置写回到 HEIF 文件的 info 中
            if icc_profile:
                heif_file.info['icc_profile'] = icc_profile
            heif_file.save(out_path, save_all=True, quality=-1)
    except Exception as e:
        raise e

input_directory = r'\\QNAP\Pictures\插画\Yande.re\cutesexyrobutts'
input_directory = r'\\DXP480TPLUS\personal_folder\Photos\yande.re\iijima_masashi'
# output_directory = r'\\DXP480TPLUS\personal_folder\Photos\yande.re\cutesexyrobutts'
output_directory = r'\\DXP480TPLUS\personal_folder\Photos\yande.re\iijima_masashi_heif'
# convert_to_heif(Path(r'\\QNAP\Pictures\插画\Yande.re\cutesexyrobutts\yande.re 1193120 areola azur_lane cutesexyrobutts erect_nipples friedrich_der_grosse_(azur_lane) garter horns naked see_through signed.png'),
#                 Path(r'C:\pyspider\t.heic'))
dir_work(input_directory, output_directory)
