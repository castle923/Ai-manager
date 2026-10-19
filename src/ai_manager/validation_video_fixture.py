"""Fresh bounded synthetic clip, using the already approved tracking runtime."""
import sys
import av
import numpy as np


def main():
    with av.open(sys.argv[1],mode='w',format='mp4') as output:
        stream=output.add_stream('mpeg4',rate=8);stream.width=256;stream.height=256;stream.pix_fmt='yuv420p'
        for index in range(8):
            pixels=np.zeros((256,256,3),dtype=np.uint8);x=48+index*8
            pixels[112:144,x:x+32]=[240,180,40]
            frame=av.VideoFrame.from_ndarray(pixels,format='rgb24')
            for packet in stream.encode(frame):output.mux(packet)
        for packet in stream.encode():output.mux(packet)


if __name__=='__main__':main()
