from pathlib import Path

def reassembler(file_name: str) -> None:
    parent    = Path(__file__).parent
    file_path = parent / file_name
    
    with open(file_path, "rb") as out_f:
        chunk_number = 1

        while True:
            chunk_name = f".part{chunk_number}"
            chunk_path = parent / chunk_name

            if not chunk_path.exists():
                break

            with open(chunk_path, "rb") as chunk_f:
                out_f.write(chunk_f.read())

            print(f"Part {chunk_number} reassembled...")
            chunk_number += 1

        print(f"File {file_name} reassembled")

    print("Enter any key to exit...")
    input()
    

if __name__ == "__main__":
    reassembler("nexo.exe")
