import select
import asyncio
from multiprocessing import shared_memory as smem


async def recv(slot: smem.SharedMemory):
    # Get the file descriptor for the shared memory slot
    fd = slot.buf.

    while True:
        # Use select to wait until the file descriptor is readable
        print("Reading...")
        readable, _, _ = select.select([fd], [], [])
        if readable:
            # Check the first 4 bytes of slot.buf
            if slot.buf[:4] != b"\x00\x00\x00\x00":
                break

    offset = int.from_bytes(slot.buf[:4], byteorder="big", signed=False)
    print(f"Received offset {offset}")
    return offset


async def main():
    slot = smem.SharedMemory(create=True, size=1024)
    # slot.buf[:4] = b"\x00\x00\x00\x00"
    offset = await recv(slot)
    print(f"Received offset {offset}")


if __name__ == "__main__":
    asyncio.run(main())