import streamlit as st
import os
import re
import shutil
import pandas as pd
import pydeck as pdk
import xml.etree.ElementTree as ET
from io import BytesIO, StringIO
import zipfile
import contextlib
import io
from processor import (
    extract_kml_from_kmz,
    delete_files_in_folder,
    remove_cdata_from_kml,
    extract_coordinates_from_kml,
    merge_kml_files
)

# Set up
st.set_page_config(page_title="KMZ/KML Processor", layout="wide")

KMZ_DIR = "kmz"
KML_DIR = "kml"
os.makedirs(KMZ_DIR, exist_ok=True)
os.makedirs(KML_DIR, exist_ok=True)

CITIES = [
    "Zagreb", "Split", "Dubrovnik", "Zadar",
    "Rijeka", "Varaždin", "Opatija", "Pula", "Poreč"
]

# -------------------
# UI
# -------------------

st.title("📍 KMZ/KML Processor for Croatian Cities")

col1, col2 = st.columns(2)
with col1:
    selected_city = st.selectbox("Choose a city", [""] + CITIES)
with col2:
    custom_city = st.text_input("Or enter a custom city")

city = custom_city.strip() if custom_city.strip() else selected_city

uploaded_files = st.file_uploader(
    "Upload KMZ or KML files",
    type=["kmz", "kml"],
    accept_multiple_files=True
)

# -------------------
# Processing Logic
# -------------------

if st.button("🚀 Process Files"):

    if not city:
        st.warning("Please select or enter a city.")
    elif not uploaded_files:
        st.warning("Please upload at least one KMZ or KML file.")
    else:
        delete_files_in_folder(KMZ_DIR)
        delete_files_in_folder(KML_DIR)

        count = 30000

        all_coords = []
        polygons = []

        st.subheader("📄 SQL Output")

        for uploaded_file in uploaded_files:
            filename = uploaded_file.name
            ext = os.path.splitext(filename)[1].lower()

            file_path = os.path.join(KMZ_DIR, filename)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.read())

            if ext == ".kmz":
                kml_path = extract_kml_from_kmz(file_path, KML_DIR)
            elif ext == ".kml":
                kml_path = os.path.join(KML_DIR, filename)
                shutil.move(file_path, kml_path)
            else:
                continue

            cleaned_kml = remove_cdata_from_kml(kml_path)

            uuid_match = re.search(r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})', filename)
            working_street_id = uuid_match.group(0) if uuid_match else city.replace(" ", "_")

            # Capture and show SQL
            output_buffer = io.StringIO()
            with contextlib.redirect_stdout(output_buffer):
                count = extract_coordinates_from_kml(cleaned_kml, count, working_street_id)

            st.code(output_buffer.getvalue(), language="sql")

            # Extract coords for table/map
            try:
                tree = ET.parse(cleaned_kml)
                root = tree.getroot()
                ns = {'kml': 'http://www.opengis.net/kml/2.2'}

                for placemark in root.findall('.//kml:Placemark', ns):
                    for coords_element in placemark.findall('.//kml:coordinates', ns):
                        coords_text = coords_element.text.strip()
                        polygon_coords = []

                        for coord in coords_text.split():
                            parts = coord.split(',')
                            if len(parts) >= 2:
                                lon, lat = float(parts[0]), float(parts[1])
                                all_coords.append({
                                    "lat": lat,
                                    "lon": lon,
                                    "file": filename
                                })
                                polygon_coords.append([lon, lat])  # 👈 build polygon

                        if polygon_coords:
                            polygons.append({
                                "name": filename,
                                "polygon": [polygon_coords]  # wrap in list (outer ring)
                            })
            except Exception as e:
                st.warning(f"Could not parse coordinates from {filename}: {e}")

        # Merge files and create ZIP
        merged_kml_path = os.path.join(KML_DIR, "merged_output.kml")
        merge_kml_files(KML_DIR, merged_kml_path, count)

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zipf:
            for f in os.listdir(KML_DIR):
                if f.endswith(".kml"):
                    zipf.write(os.path.join(KML_DIR, f), arcname=f)
        zip_buffer.seek(0)

        st.success("✅ Processing complete! Your files are ready.")

        # Table view if individual coordinates collected
        if all_coords:
            df = pd.DataFrame(all_coords)
            st.subheader("📋 Coordinate Table")
            st.dataframe(df)

        # Map polygon zones
        if polygons:
            poly_df = pd.DataFrame(polygons)
            for i, poly in enumerate(poly_df["polygon"]):
                if poly and isinstance(poly, list) and isinstance(poly[0], list):
                    ring = poly[0]
                    if ring[0] != ring[-1]:
                        st.warning(f"Polygon {i} is not closed.")
                        st.write("First:", ring[0])
                        st.write("Last:", ring[-1])



            st.subheader("🗺️ Zone Map")

            layer = pdk.Layer(
                "PolygonLayer",
                poly_df,
                get_polygon="polygon",
                get_fill_color="[0, 0, 255, 40]",    # Transparent blue
                get_line_color="[0, 0, 255, 200]",   # Solid border
                line_width_min_pixels=1,
                pickable=True,
                stroked=True,
                filled=True,
            )

            first_polygon = poly_df["polygon"].iloc[0]
            first_ring = first_polygon[0]
            first_point = first_ring[0]
            lon, lat = first_point

            view_state = pdk.ViewState(
                latitude=lat,
                longitude=lon,
                zoom=14,
                pitch=0,
            )

            st.pydeck_chart(pdk.Deck(
                map_style="mapbox://styles/mapbox/light-v9",
                initial_view_state=view_state,
                layers=[layer],
                tooltip={"text": "Zone from {name}"}
            ))

        # Download button
        st.download_button(
            label="📥 Download All Processed KMLs (ZIP)",
            data=zip_buffer,
            file_name=f"{city}_kml_output.zip",
            mime="application/zip"
        )
