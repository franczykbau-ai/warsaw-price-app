import math
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Wycena PRO – Warszawa", layout="centered")

st.title("Wycena mieszkania PRO – Warszawa")
st.caption("Wersja PRO: więcej parametrów, korekty za standard, piętro, parking i odległość od metra + opcjonalne porównanie do Twoich „comps” (CSV).")

@st.cache_data
def load_prices():
    return pd.read_csv("data/warsaw_prices.csv")

@st.cache_data
def load_metro():
    return pd.read_csv("data/metro_stations.csv")

prices = load_prices()
metro = load_metro()

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2-lat1)
    dl = math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

def nearest_metro(lat, lon):
    dmin = 1e9
    best = None
    for _, r in metro.iterrows():
        d = haversine_km(lat, lon, float(r.lat), float(r.lon))
        if d < dmin:
            dmin = d
            best = r
    return best, dmin

def geocode(query: str):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "addressdetails": 1, "limit": 1}
    headers = {"User-Agent": "WarsawPriceCheckerPRO/1.0 (personal-use)"}
    r = requests.get(url, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    arr = r.json()
    if not arr:
        return None
    return arr[0]

def pick_district(addr: dict):
    # Best-effort: Nominatim isn't always consistent
    for k in ["city_district", "suburb", "borough"]:
        if k in addr:
            return addr[k]
    return None

with st.sidebar:
    st.header("Ustawienia PRO")
    tol = st.slider("Tolerancja (widełki +/-)", min_value=3, max_value=20, value=7, step=1)
    st.caption("Używane do decyzji: OK / zawyżona / okazja.")
    st.divider()
    st.subheader("Korekty (możesz zmienić)")
    k_std = st.slider("Korekta za standard (słaby→premium) łącznie", 0, 20, 10, 1)
    k_floor = st.slider("Korekta za piętro (parter/ostatnie) max", 0, 10, 5, 1)
    k_parking = st.slider("Premia za miejsce w garażu", 0, 8, 3, 1)
    st.divider()
    st.subheader("Dane odniesienia")
    st.write("Bazą jest mediana ceny za m² w dzielnicy z pliku `data/warsaw_prices.csv`.")
    st.write("Dodatkowo możesz wgrać własne porównywalne oferty (CSV) i wtedy appka policzy medianę z Twoich danych.")

st.subheader("Dane mieszkania")

c1, c2 = st.columns(2)
with c1:
    address = st.text_input("Adres (ulica + nr)", placeholder="np. ul. Wolska 50")
with c2:
    district_manual = st.selectbox("Dzielnica (jeśli chcesz ręcznie)", ["(auto)"] + prices["district"].tolist(), index=0)

c3, c4 = st.columns(2)
with c3:
    area = st.number_input("Powierzchnia (m²)", min_value=10.0, max_value=200.0, value=45.0, step=0.5)
with c4:
    rooms = st.selectbox("Liczba pokoi", [1,2,3,4], index=1)

price = st.number_input("Cena ofertowa (zł)", min_value=100000, max_value=10000000, value=680000, step=5000)

c5, c6, c7 = st.columns(3)
with c5:
    standard = st.select_slider("Standard", options=["słaby","OK","dobry","premium"], value="dobry")
with c6:
    floor = st.number_input("Piętro (parter=0)", min_value=0, max_value=40, value=3, step=1)
with c7:
    parking = st.selectbox("Parking", ["brak", "naziemne", "garaż"], index=2)

year = st.number_input("Rok budowy (orientacyjnie)", min_value=1900, max_value=2030, value=2015, step=1)

st.subheader("Porównywalne oferty (opcjonalnie)")
st.caption("Wgraj własne „comps” (np. z 5–30 ofert) jako CSV z kolumnami: price, area, lat, lon (opcjonalnie rooms, year).")
uploaded = st.file_uploader("Wgraj CSV z porównywalnymi ofertami", type=["csv"])

run = st.button("Sprawdź cenę (PRO)", type="primary", use_container_width=True)

def standard_factor(std):
    # maps to -k..+k (half range)
    m = {"słaby": -1.0, "OK": -0.3, "dobry": 0.3, "premium": 1.0}
    return m.get(std, 0.0)

def floor_factor(f):
    # penalty for ground and very high last floors (approx; user can refine)
    if f == 0:
        return -1.0
    if f >= 10:
        return -0.4
    return 0.2

def parking_factor(p):
    if p == "garaż":
        return 1.0
    if p == "naziemne":
        return 0.4
    return 0.0

if run:
    if not address:
        st.error("Wpisz adres (ulica + numer).")
        st.stop()

    q = f"{address}, Warszawa, Polska"
    try:
        g = geocode(q)
    except Exception as e:
        st.error(f"Nie udało się pobrać lokalizacji: {e}")
        st.stop()
    if not g:
        st.error("Nie znalazłem tego adresu. Spróbuj dopisać numer budynku lub dzielnicę.")
        st.stop()

    lat = float(g["lat"]); lon = float(g["lon"])
    addr = g.get("address", {})
    d_auto = pick_district(addr)

    # Choose district
    if district_manual != "(auto)":
        district = district_manual
        district_note = "ręcznie"
    else:
        district_note = "auto"
        district = None
        if d_auto:
            for d in prices["district"].tolist():
                if d.lower() in d_auto.lower() or d_auto.lower() in d.lower():
                    district = d
                    break
        if district is None:
            district = st.selectbox("Nie rozpoznano dzielnicy – wybierz:", options=prices["district"].tolist(), index=0)
            district_note = "ręcznie (po niepewnym auto)"

    base_median = float(prices.loc[prices["district"] == district, "median_price_pln_m2"].iloc[0])

    # Nearest metro
    stn, dkm = nearest_metro(lat, lon)
    # metro adjustment (simple): closer => higher fair price; far => lower
    # scale: 0 km => +4%, 2 km => 0%, 4 km => -4%
    metro_adj = 0.0
    if dkm <= 2:
        metro_adj = (2 - dkm) / 2 * 0.04
    elif dkm <= 4:
        metro_adj = -(dkm - 2) / 2 * 0.04
    else:
        metro_adj = -0.04

    # Feature adjustments in % (bounded)
    std_adj = standard_factor(standard) * (k_std/100) * 0.5
    fl_adj = floor_factor(floor) * (k_floor/100) * 0.5
    pk_adj = parking_factor(parking) * (k_parking/100)

    # rooms/year minor tweaks
    rooms_adj = 0.0
    if rooms == 1:
        rooms_adj = 0.01
    elif rooms == 3:
        rooms_adj = -0.01
    elif rooms >= 4:
        rooms_adj = -0.02

    year_adj = 0.0
    if year >= 2018:
        year_adj = 0.01
    elif year <= 1980:
        year_adj = -0.01

    fair_pm2 = base_median * (1 + metro_adj + std_adj + fl_adj + pk_adj + rooms_adj + year_adj)

    # Optional comps-based fair value
    comps_used = False
    comp_pm2 = None
    if uploaded is not None:
        comps = pd.read_csv(uploaded)
        # minimal required columns
        if "price" in comps.columns and "area" in comps.columns:
            comps["pm2"] = comps["price"] / comps["area"]
            if "lat" in comps.columns and "lon" in comps.columns:
                comps["dist_km"] = comps.apply(lambda r: haversine_km(lat, lon, float(r["lat"]), float(r["lon"])), axis=1)
                # keep within 1.5 km by default
                comps2 = comps[comps["dist_km"] <= 1.5].copy()
                if len(comps2) >= 5:
                    comp_pm2 = float(comps2["pm2"].median())
                    comps_used = True
                    comps_show = comps2.sort_values("dist_km").head(10)
                else:
                    comps_show = comps.sort_values("pm2").head(10)
            else:
                comp_pm2 = float(comps["pm2"].median())
                comps_used = True
                comps_show = comps.sort_values("pm2").head(10)
        else:
            st.warning("CSV powinien mieć kolumny: price, area (opcjonalnie lat, lon). Pomijam comps.")

    # Blend: if comps provided, use weighted average 70% comps, 30% model
    if comps_used and comp_pm2:
        fair_pm2_blend = 0.7 * comp_pm2 + 0.3 * fair_pm2
    else:
        fair_pm2_blend = fair_pm2

    offer_pm2 = price / area
    low = fair_pm2_blend * (1 - tol/100)
    high = fair_pm2_blend * (1 + tol/100)

    st.subheader("Wynik (PRO)")

    if offer_pm2 > high:
        st.error("CENA ZAWYŻONA ❌")
    elif offer_pm2 < low:
        st.success("WYGLĄDA NA OKAZJĘ ✅")
    else:
        st.info("CENA OK / RYNKOWA ⚖️")

    st.write(f"**Dzielnica:** {district} ({district_note})")
    st.write(f"**Cena ofertowa:** {price:,.0f} zł • **Metraż:** {area:.1f} m² • **Cena za m²:** {offer_pm2:,.0f} zł/m²")
    st.write(f"**Poziom odniesienia (PRO, po korektach):** {fair_pm2_blend:,.0f} zł/m²")
    st.write(f"**Widełki rynkowe (+/- {tol}%):** {low:,.0f} – {high:,.0f} zł/m²")

    st.divider()
    st.caption("Najbliższe metro (orientacyjnie)")
    st.write(f"**{stn.station}** ({stn.line}) — ~**{dkm:.2f} km**")

    st.divider()
    st.caption("Lokalizacja")
    st.map(pd.DataFrame({"lat":[lat], "lon":[lon]}))

    if comps_used:
        st.divider()
        st.caption("Twoje porównywalne oferty (podgląd)")
        st.dataframe(comps_show, use_container_width=True)

    st.divider()
    st.caption("Jak to interpretować")
    st.write(
        "To jest **wstępna ocena**. Dla decyzji inwestycyjnej zawsze sprawdź: KW (dział III/IV), czynsz administracyjny, "
        "hałas, stan techniczny, plan miejscowy, oraz realne czynsze najmu w okolicy."
    )
