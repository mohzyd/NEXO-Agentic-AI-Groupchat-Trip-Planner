from pathlib import Path

def spliter(file_name: str, size_in_mb: int = 5) -> None:
    file_path = Path(__file__).parent / file_name
    if not file_path.exists():
        raise FileNotFoundError(f"File {file_name} not found")
    
    size_in_bytes = size_in_mb * 1024 * 1024
    with open(file_path, "rb") as f:
        chunk_number = 1

        while True:
            chunk_data = f.read(size_in_bytes)
            if not chunk_data:
                break

            chunk_name = f"{file_name}.part{chunk_number}"
            with open(chunk_name, "wb") as chunk_file:
                chunk_file.write(chunk_data)
            
            print(f"Part {chunk_number} created...")
            chunk_number += 1

    print(f"File {file_name} split into {chunk_number - 1} parts")

if __name__ == "__main__":
    spliter("nexo.exe")