import os
import re
import sys
import json
import time
import uuid
import struct
import codecs
import argparse

from sanic import Sanic
import sanic.response as response
from sanic.websocket import WebSocketProtocol
import websockets

import socket
import select

src_root = os.path.dirname(os.path.abspath(__file__))

app = Sanic("Exp control")

app.static('/css', src_root)
app.static('/js', src_root)


config = {
    "host": "0.0.0.0",
    "port": 8000,
    "debug": True,
    "workers": 1,

    "tmp_folder": "./tmp",
    "save_folder": "./saved_wavs"
}

os.makedirs(config["tmp_folder"], exist_ok=True)
os.makedirs(config["save_folder"], exist_ok=True)



def load_template(template):
    with codecs.open(os.path.join(src_root, template), 'r', 'utf-8') as f:
        template = f.read()
        return template


def _render_template(template, **kwargs):
    # print(kwargs)
    for k in kwargs:
        template = re.sub("{{\s*" + k + "\s*}}", kwargs[k], template)
    return template


template_cache = {}
def render_template(template, **kwargs):
    global template_cache
    if template not in template_cache:  # TODO: reenable template cache
        template_cache[template] = load_template(template)
    return _render_template(template_cache[template], **kwargs)


def render_table(header, data):
    thead = "".join(f"<th>{s}</th>" for s in header)
    thead = f"<thead><tr>{thead}</tr></thead>"

    tbody = "</tr><tr>".join("".join(f"<td>{c}</td>" for c in row)  for row in data)
    result = f'<div class="table-responsive"><table class="table table-striped"><thead><tr>{thead}</tr></thead><tbody><tr>{tbody}</tr></tbody></table></div>'

    return result


SUBCHUNK1_SIZE_PCM = 16;
SUBCHUNK2_SIZE_NOT_SET = 0x7FFFFFFF;


def make_header(wav, header):
    chunk_size = header["data_length"]

    subchunk1_size = struct.unpack("I", wav[16:20])[0]

    if subchunk1_size == SUBCHUNK1_SIZE_PCM:
        start_pos = 36
    elif  subchunk1_size == SUBCHUNK1_SIZE_PCM + 2: #sizeof(short)
        #  Read any extra values
        fmt_extra_size = struct.unpack("H", wav[36:38])[0] # UInt16
        start_pos = 38 + fmt_extra_size
    else:
        raise ValueError("Unexpected subchunk1_size %s" % str(subchunk1_size))



    # chunk 2
    # Подцепочка "data" содержит аудио-данные и их размер.

    # uint subchunk2Id;
    #uint subchunkSizeBytes;
    while True:
        subchunk2Id =  wav[start_pos:start_pos+4] # struct.unpack("I", )[0]
        subchunkSizeBytes = struct.unpack("I", wav[start_pos+4: start_pos+8])[0]

        start_pos = start_pos + 8
        if subchunk2Id == b"LIST":
            # just skip whole subchunk
            start_pos +=  subchunkSizeBytes
        else:
            break

    res = wav[:4] + struct.pack("I", chunk_size) + wav[8:start_pos -4] + struct.pack("I", chunk_size)
    return res


def fix_wav_length(src_path, dst_path):  # sets proper wav length in wav header
    with open(src_path, 'rb') as src:
        data = src.read()
        header = wav_header(data)

        new_header = make_header(data, header)
        new_data = new_header + data[header["start_pos"]: header["start_pos"] + header["data_length"]]

    with open(dst_path, 'wb') as dst:
            dst.write(new_data)


def wav_header(wav):  # parses wav header
    res = {}

    chunk_id = wav[:4]
    if chunk_id != b'RIFF':
        raise ValueError("Expected RIFF")

    res["chunk_size"] = wav[4:8]

    wav_format =  wav[8:12]
    if wav_format != b'WAVE':
        raise ValueError("Expected WAVE format")

    subchunk1_id = wav[12:16]
    if subchunk1_id != b'fmt ':
        raise ValueError("Bad subchunk1 id %s" % str(subchunk1_id))

    subchunk1_size = struct.unpack("I", wav[16:20])[0]

    audio_format = struct.unpack("H", wav[20:22])[0]  # UInt16 / ushort
    if audio_format != 1:
        raise ValueError("Expected PCM wav audio format, got %s" % str(audio_format))


    res["num_channels"] = struct.unpack("H", wav[22:24])[0]   # UInt16
    res["sampling_rate"] = struct.unpack("I", wav[24:28])[0]

    byte_rate = struct.unpack("I", wav[28:32])[0] # UInt32
    block_align = struct.unpack("H", wav[32:34])[0]  # UInt16

    res["bits_per_sample"] = struct.unpack("H", wav[34:36])[0] # UInt16

    if subchunk1_size == SUBCHUNK1_SIZE_PCM:
        start_pos = 36
    elif  subchunk1_size == SUBCHUNK1_SIZE_PCM + 2: #sizeof(short)
        #  Read any extra values
        fmt_extra_size = struct.unpack("H", wav[36:38])[0] # UInt16
        start_pos = 38 + fmt_extra_size
    else:
        raise ValueError("Unexpected subchunk1_size %s" % str(subchunk1_size))


    # chunk 2
    # Подцепочка "data" содержит аудио-данные и их размер.

    # uint subchunk2Id;
    #uint subchunkSizeBytes;
    while True:
        subchunk2Id =  wav[start_pos:start_pos+4] # struct.unpack("I", )[0]
        subchunkSizeBytes = struct.unpack("I", wav[start_pos+4: start_pos+8])[0]
        start_pos = start_pos + 8
        if subchunk2Id == b"LIST":
            # just skip whole subchunk
            start_pos +=  subchunkSizeBytes
        else:
            break

    if subchunk2Id != b"data":
        raise ValueError("Expected data chunk at %s" % start_pos)


#     if subchunkSizeBytes == SUBCHUNK2_SIZE_NOT_SET:

    # force recalculation of wav length
    # hack to support custom file length calculation
    # this does not check if there are other subchunks after "data" in the file

    sizeInBytesLong = len(wav) - start_pos
    if sizeInBytesLong > 2**33 -1:
        raise ValueError("Wav file is too long")

    res["data_length"] = sizeInBytesLong
#     else:
#         res["data_length"] = subchunkSizeBytes

    res["start_pos"] = start_pos
    return res


def read_wav(data, scroll_past_header=True):
    header = wav_header(data)

    if scroll_past_header:
        wav = data[header["start_pos"]: header["start_pos"] + header["data_length"]]
    else:
        wav = data

    #return wav, header["sampling_rate"], header["num_channels"], header["bits_per_sample"], header
    return header, wav


@app.route("/")
async def index(request):
    return response.html(render_template(
        "index.html"
    ))

@app.websocket('/ws')
async def pred(request, ws):
    id = str(uuid.uuid4())
    await ws.send(id)

    save_path = os.path.join(config["tmp_folder"], id)

    while True:
        try:
            body = await ws.recv()
            _, wav = read_wav(body, scroll_past_header=True)



            if not os.path.exists(save_path):  # saving first chunk with header
                with open(save_path, 'wb') as f:
                    f.write(body)
            else:  # for every other chunk skip header, saving just audio
                with open(save_path, 'ab') as f:
                    f.write(wav)
        except Exception as e:
            print("Error", type(e), e)
            print("Web socket closed")
            if os.path.exists(save_path): # fix wav header to have proper audio duration
                dst_path = os.path.join(config["save_folder"], id + "-fixed.wav")
                fix_wav_length(save_path, dst_path)
            break


@app.route("/stop")
async def stop(request):
    id = request.args.get("id", None)
    if id:
        return response.json({"status": "stopped", "id": id})
        src_path = os.path.join(config["tmp_folder"], id)
        if os.path.exists(src_path):
            dst_path = os.path.join(config["save_folder"], id + "-fixed.wav")
            fix_wav_length(src_path, dst_path)
            return response.json({"status": "stopped", "id": id})
        else:
            return response.json({"status": "not found", "id": id})
    return response.json({"status": "error", "reason": "no id provided"})


if __name__ == "__main__":
    app.run(
        host=config["host"],
        port=config["port"],
        debug=config["debug"],
        workers=config["workers"]
    )
