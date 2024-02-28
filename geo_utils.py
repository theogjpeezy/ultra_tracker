from geopy.distance import geodesic

def interpolate_between_points(points, interval_distance):
    interpolated_points = []

    for i in range(len(points) - 1):
        point1 = {"latitude": points[i][0], "longitude": points[i][1]}
        point2 = {"latitude": points[i + 1][0], "longitude": points[i + 1][1]}

        # Convert latitude and longitude to (lat, lon) tuples
        coords1 = (point1["latitude"], point1["longitude"])
        coords2 = (point2["latitude"], point2["longitude"])

        # Calculate the distance between consecutive points
        distance_between_points = geodesic(coords1, coords2).miles

        # Check if interpolation is needed
        if distance_between_points > interval_distance:
            # Calculate the number of intervals needed
            num_intervals = int(distance_between_points / interval_distance)

            # Calculate the step size for latitude and longitude
            lat_step = (point2["latitude"] - point1["latitude"]) / num_intervals
            lon_step = (point2["longitude"] - point1["longitude"]) / num_intervals

            # Generate interpolated points
            interpolated_points.extend([[point1["latitude"] + j * lat_step,
                                         point1["longitude"] + j * lon_step]
                                        for j in range(1, num_intervals)])

    return interpolated_points

# Example usage:
points_list = []

interval_distance = 0.11  # in miles

interpolated_points = interpolate_between_points(points_list, interval_distance)

# Output the result
for point in interpolated_points:
    print(f"Latitude: {point[0]}, Longitude: {point[1]}")

