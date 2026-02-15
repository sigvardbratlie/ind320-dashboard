"""
Interactive Map and Snow Drift Analysis Page

Displays an interactive map of Norwegian price areas with electricity data overlays
and performs snow drift calculations based on meteorological data.
"""
import streamlit as st
import pandas as pd
import folium
import json
from streamlit_folium import st_folium
import os
from typing import Optional
from utilities import (
    init, sidebar_setup, get_elhub_data, init_connection,
    el_sidebar, get_weather_data, extract_coordinates
)
from snow_drift import snowdrift
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize


# =================================
#          FUNCTION DEFINITIONS
# =================================
@st.cache_data(ttl=600)
def load_geodata(dfg: pd.DataFrame) -> Optional[dict]:
    """
    Load and enrich GeoJSON data with electricity quantity values.

    Args:
        dfg: DataFrame with electricity data grouped by price area.

    Returns:
        GeoJSON dictionary with enriched properties, or None if file not found.
    """
    try:
        with open("data/file.geojson") as f:
            gj = json.load(f)
    except FileNotFoundError:
        st.error("GeoJSON file not found.")
        return None
    except Exception as e:
        st.error(f"An error occurred while loading the GeoJSON file: {e}")
        return None
    
    for feature in gj.get("features", []):
        label = feature.get("properties", {}).get('ElSpotOmr','').replace(" ","")
        feature.get("properties", {})['ElSpotOmr'] = label
        kwh = dfg.loc[dfg['pricearea'] == label, 'quantitymwh'].values
        if len(kwh) > 0:
            feature['properties']['quantitymwh'] = float(kwh[0])
        else:
            feature['properties']['quantitymwh'] = 0.0

    return gj
    
def get_color(value: float) -> str:
    """
    Convert a value to a hex color using the current colormap.

    Args:
        value: Numeric value to convert to color.

    Returns:
        Hex color string.
    """
    rgba = colormap(norm(value))
    return '#{:02x}{:02x}{:02x}'.format(int(rgba[0]*255), int(rgba[1]*255), int(rgba[2]*255))


def load_map(gj: dict, coordinates: Optional[tuple[float, float]] = None) -> folium.Map:
    """
    Create a Folium map with electricity data overlays.

    Args:
        gj: GeoJSON data for price areas.
        coordinates: Tuple of (latitude, longitude) for map center.

    Returns:
        Folium Map object with choropleth and markers.
    """    
    m = folium.Map(location=coordinates, zoom_start=4,tiles='CartoDB positron') #create map

    folium.Choropleth(
                geo_data=gj,
                name='Production',
                data=dfg,
                columns=['pricearea', 'quantitymwh'],
                key_on='feature.properties.ElSpotOmr',
                fill_color=colormap.name,
                fill_opacity=0.7,
                line_opacity=0.2,
                line_color='black',
                legend_name='Average MWh',
                popup=folium.features.GeoJsonPopup(
                    fields=['ElSpotOmr', 'quantitymwh'],
                    aliases=['Price Area', 'MWh']
                )
            ).add_to(m)
    
    folium.GeoJson(
                gj,
                tooltip=folium.features.GeoJsonTooltip(
                    fields=['ElSpotOmr', 'quantitymwh'],
                    aliases=['Price Area', 'MWh'])
            ).add_to(m)
    for feature in gj.get("features", []):
        if price_area == feature['properties']['ElSpotOmr'].replace(" ",""):
            folium.GeoJson(
                feature,
                style_function=lambda x,: {
                    'fillColor': colormap.name,
                    'color': "black",
                    'weight': 3,
                    'fillOpacity': 0.4,
                },
                tooltip=folium.features.GeoJsonTooltip(
                    fields=['ElSpotOmr', 'quantitymwh'],
                    aliases=['Price Area', 'MWh'])
            ).add_to(m)

    lat, lon = coordinates
    folium.Marker(
            location=[lat, lon],
            popup=city,
            icon=folium.Icon(color='green', icon='info-sign')
        ).add_to(m)

    folium.LayerControl().add_to(m)
    return m

def update_location() -> None:
    """
    Update session state with the selected location from the map click.

    This callback function extracts coordinates and price area from the map
    interaction and updates the session state.
    """
    try:
        prop = st.session_state.get("my_map",{}).get("last_active_drawing",{}).get("properties",{})
        coor = st.session_state.get("my_map",{}).get("last_clicked",{})
        lat,lon = coor.get("lat"), coor.get("lng")
        selected_coordinates = (lat,lon)    
        if prop and selected_coordinates != (None,None):
            st.session_state.location.update({"coordinates": selected_coordinates,
                                      "city": None,
                                      "price_area": prop.get("ElSpotOmr","").replace(" ","")})
        
        
    except (AttributeError, TypeError) as e:
        pass
    except Exception as e:
        st.error(f"Error in callback: {e}")


# =================================
#          PAGE SETUP
# =================================
st.set_page_config(
    page_title="Map Selection",
    page_icon="🗺️",
)
st.title("Map and Snow Drift Analysis")

init()
init_connection()
sidebar_setup()
el_sidebar()

# =================================
#          LOAD DATA
# =================================

coordinates = st.session_state.get("location",{}).get("coordinates", None)
city = st.session_state.get("location",{}).get("city", None)
price_area = st.session_state.get("location",{}).get("price_area", "NO1")

df_el = get_elhub_data(st.session_state["client"],dataset=st.session_state.group.get("name"),dates = st.session_state.dates,filter_group=True,aggregate_group=False)

dfg = df_el.groupby("pricearea")["quantitykwh"].mean().reset_index()
dfg["quantitymwh"] = dfg["quantitykwh"] // 1e3  # Convert to kWh
norm = Normalize(vmin=dfg["quantitymwh"].min(), vmax=dfg["quantitymwh"].max())
#colormap = plt.cm.Blues  # eller RdYlGn, Viridis osv
import matplotlib as mpl
colormap =  mpl.colormaps['viridis']

# =================================
#           FOLIUM MAP
# =================================
st.info(f"Showing coordinates lat: {coordinates[0]:.3f}, lon: {coordinates[1]:.3f}")

cols = st.columns(2)
with cols[0]:
    st.subheader("🗺️ Map Selection of Price Areas 🔋⚡️")
    gj = load_geodata(dfg = dfg)
    m = load_map(gj, coordinates=coordinates)
    st_folium(m,width = "100%",height=600,
                on_change=update_location,
                key="my_map")


#=================================
#       SNOW DRIFT ANALYSIS
#=================================
with cols[1]:
    st.subheader("❄️ Snow Drift Analysis")
    snow_container = st.container(width="stretch")
    with snow_container:
        df_w = get_weather_data(coordinates=coordinates, dates = st.session_state.dates, set_time_index=False)
        if isinstance(df_w, pd.DataFrame) and not df_w.empty:
            plot, fence_df,yearly_df, overall_avg = snowdrift(df = df_w)
            st.plotly_chart(plot,use_container_width=True)
            
            yearly_df_disp = yearly_df.copy()
            yearly_df_disp["Qt (tonnes/m)"] = yearly_df_disp["Qt (kg/m)"] / 1000
            

            overall_avg_tonnes = overall_avg / 1000

            snow_df = pd.merge(yearly_df, fence_df, on="season")
            snow_df.set_index("season", inplace=True)
            snow_df.drop(columns=["Control"], inplace=True)
            st.dataframe(snow_df.T.round(2).style.format("{:,.2f}"))



with st.expander("Data sources"):
    st.write(f'Meteo API https://archive-api.open-meteo.com')
    st.write(f'Elhub API https://api.elhub.no')