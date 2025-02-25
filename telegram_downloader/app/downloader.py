import os, sys
import hashlib
import time
from datetime import datetime
from telethon.tl.types import MessageMediaDocument, MessageEntityUrl


async def Start(
    client,
    channel,
    static_files,
    start_id: int = 0,
    end_id: int = -1,
    interactive=False,
):
    """
    Downloads files from a Telegram channel, saves them with SHA256 hashes,
    creates metadata text files for each post with details, and tracks download speed.

    Args:
        client: The authenticated Telegram client instance.
        channel: The channel entity fetched from the Telegram API.

    Returns:
        None
        :param interactive:
    """
    if interactive:
        start_id = input("Enter the MIN post ID: ")
        if start_id.isnumeric() or start_id == "-1":
            start_id = int(start_id)
        else:
            start_id = int(input("Need a numeric value, try again:"))
        end_id = input("Enter the MAX post ID (or -1 for the latest): ")
        if end_id.isnumeric() or end_id == "-1":
            end_id = int(end_id)
        else:
            end_id = int(input("Need a numeric value, try again:"))

    channel_id = channel.id
    save_path = os.path.join(os.getcwd(), "channels" + os.sep + str(channel_id))

    # Create a directory for the channel if it doesn't exist
    os.makedirs(save_path, exist_ok=True)

    print(f"[INFO] Saving files to: {save_path}")

    # Tracking stats
    total_downloaded_bytes = 0
    start_time = time.time()

    # Loop through messages from start_id to end_id
    async for message in client.iter_messages(
        channel, min_id=start_id - 1, max_id=(end_id if end_id else None)
    ):
        if not message.media and not message.text:
            # print(f"[SKIPPED] No media or text in message {message.id}")
            sys.stdout.flush()
            continue

        # Metadata variables
        post_id = message.id
        author = (
            getattr(message.from_id, "user_id", "Unknown")
            if message.from_id
            else "Unknown"
        )
        date = message.date.isoformat() if message.date else "Unknown"
        text = message.text or "No text"
        hashes = []

        # Extract links from the message text
        links = []
        if message.entities:
            for entity in message.entities:
                if isinstance(entity, MessageEntityUrl):
                    links.append(
                        message.text[entity.offset : entity.offset + entity.length]
                    )

        # Check if metadata file exists
        metadata_path = os.path.join(save_path, f".POST-ID-{post_id}.log")
        if os.path.exists(metadata_path):
            # print(f"[SKIPPED] Metadata for post {post_id} already exists. Skipping post.")
            sys.stdout.flush()
            continue

        # Download files if media is present
        if message.media and isinstance(message.media, MessageMediaDocument):
            file_name = message.file.name or "unknown"
            file_ext = os.path.splitext(file_name)[-1] or ""

            # Generate SHA256 hash for the file
            file_bytes = await client.download_file(message.media)
            sha256_hash = hashlib.sha256(file_bytes).hexdigest()
            hashes.append(sha256_hash)

            match static_files["naming"]:
                case 1:  # sha256 + extension
                    file_path = os.path.join(save_path, f"{sha256_hash}{file_ext}")
                case 2:  # original filenames:
                    file_path = os.path.join(save_path, f"{file_name}{file_ext}")
                case 3:  # original filenames + sha256 + ext:
                    file_path = os.path.join(
                        save_path, f"{file_name}_{sha256_hash}{file_ext}"
                    )
                case _:
                    # Optional: handle unexpected values
                    raise ValueError(
                        f"Unexpected naming option: {static_files['naming']}"
                    )

            # Save the file if it doesn't already exist
            if not os.path.exists(file_path):
                with open(file_path, "wb") as f:
                    f.write(file_bytes)
                file_size = len(file_bytes) / (1024 * 1024)  # Convert bytes to MB
                total_downloaded_bytes += len(file_bytes)

                # Calculate elapsed time and avg speed
                elapsed_time = time.time() - start_time
                avg_speed = (
                    (total_downloaded_bytes / (1024 * 1024)) / elapsed_time
                    if elapsed_time > 0
                    else 0
                )

                print(f"[DOWNLOADED] {file_path} ({file_size:.2f} MB)")
                print(
                    f"[STATS] Total: {(total_downloaded_bytes / (1024 * 1024)):.2f} MB | Avg Speed: {avg_speed:.2f} MB/s"
                )
                sys.stdout.flush()
            else:
                print(f"[SKIPPED] File already exists: {file_path}")
                sys.stdout.flush()

        # Save metadata as a .txt file
        with open(metadata_path, "w", encoding="utf-8") as meta_file:
            meta_file.write(f"Post ID: {post_id}\n")
            meta_file.write(f"Author: {author}\n")
            meta_file.write(f"Date: {date}\n")
            meta_file.write(f"Hashes: {', '.join(hashes) if hashes else 'No files'}\n")
            meta_file.write(f"Text:\n{text}\n")
            if links:
                meta_file.write(f"Links:\n{', '.join(links)}\n")

        print(f"[METADATA SAVED] {metadata_path}")
        sys.stdout.flush()
    print("[INFO] Download completed.")
    total_time = time.time() - start_time
    avg_speed = (
        (total_downloaded_bytes / (1024 * 1024)) / total_time if total_time > 0 else 0
    )
    print(
        f"[FINAL STATS] Total Downloaded on channel {channel} : {channel_id}: {(total_downloaded_bytes / (1024 * 1024)):.2f} MB | Avg Speed: {avg_speed:.2f} MB/s | Total Time: {total_time:.2f} seconds"
    )
    sys.stdout.flush()
