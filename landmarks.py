"""
Reach landmarks between Bull Shoals Dam and White Hole: pinned GPS
coordinates and the river miles derived from them.

Coordinates are points in the river beside each landmark, pinned by Brian.
River miles are the cumulative straight-line (haversine) distance along the
landmark chain, scaled so White Hole lands exactly on the travel model's
calibrated 7.0 miles (water_calculator.calculate_travel_time). The raw chord
sum (~6.73 mi) undercuts the river's meanders between points; scaling keeps
each landmark at its GPS-derived fraction of the reach while preserving the
His Place calibration at the endpoint.
"""

import math

WHITE_HOLE_MILE = 7.0  # the travel model's calibrated dam-to-White Hole distance

# (display name, (lat, lon)), ordered downstream from the dam
LANDMARK_COORDS = [
    ("Bull Shoals Dam", (36.365933396896075, -92.57517125493467)),
    ("White River State Park", (36.355581428703694, -92.59449628292708)),
    ("Copper John's", (36.344313392658236, -92.58458283870175)),
    ("Cane Island", (36.34317267222181, -92.56930497596221)),
    ("Gaston's", (36.347597191038865, -92.55540040484095)),
    ("The Honey Hole", (36.351399311192914, -92.53458646255478)),
    ("Big Island", (36.33950842714197, -92.52840665295527)),
    ("The White Hole", (36.329897607316106, -92.53355649411128)),
]


def haversine_miles(coord_a, coord_b):
    """Great-circle distance in miles between two (lat, lon) points."""
    earth_radius_miles = 3958.7613
    lat1, lon1 = map(math.radians, coord_a)
    lat2, lon2 = map(math.radians, coord_b)
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * earth_radius_miles * math.asin(math.sqrt(h))


def _river_miles():
    chord_totals = [0.0]
    for (_, prev), (_, cur) in zip(LANDMARK_COORDS, LANDMARK_COORDS[1:]):
        chord_totals.append(chord_totals[-1] + haversine_miles(prev, cur))
    scale = WHITE_HOLE_MILE / chord_totals[-1]
    return [round(total * scale, 2) for total in chord_totals]


# (display name, river mile), same order as LANDMARK_COORDS
LANDMARK_MILES = [
    (name, mile)
    for (name, _), mile in zip(LANDMARK_COORDS, _river_miles())
]

GASTONS_MILE = dict(LANDMARK_MILES)["Gaston's"]
