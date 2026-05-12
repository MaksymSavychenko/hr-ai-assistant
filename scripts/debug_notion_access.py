import os
from pathlib import Path

from dotenv import load_dotenv
from notion_client import Client


def main():
    load_dotenv()
    token = os.getenv("NOTION_TOKEN", "")
    database_id = os.getenv("NOTION_DATABASE_ID", "")

    if not token:
        raise ValueError("NOTION_TOKEN is missing in .env")

    print("NOTION_DATABASE_ID from .env:", database_id)
    print("Length:", len(database_id))
    print()

    client = Client(auth=token)

    print("Searching for pages/databases visible to integration...")
    response = client.search(page_size=50)
    results = response.get("results", [])

    if not results:
        print("No results found. Integration likely has no shared pages/databases.")
        return

    print(f"Found {len(results)} visible objects:\n")

    for item in results:
        obj_type = item.get("object", "")
        item_id = item.get("id", "")
        parent = item.get("parent", {})
        parent_type = parent.get("type", "")

        title = "Untitled"
        if item.get("properties", {}).get("title"):
            title_parts = item["properties"]["title"].get("title", [])
            title = "".join(x.get("plain_text", "") for x in title_parts) or title

        print(f"- object={obj_type} id={item_id} parent_type={parent_type} title={title}")

        if item.get("object") == "database":
            data_sources = item.get("data_sources", [])
            for ds in data_sources:
                print(f"  data_source_id={ds.get('id', '')}")


if __name__ == "__main__":
    main()
