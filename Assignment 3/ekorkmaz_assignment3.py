"""Assignment 3: Spatial Overlays and Areal Interpolation.
Complete three functions using ArcPy and pathlib.Path. Prepare and project
copies before analysis; preserve inputs and avoid hardcoded paths or values.
Check input paths, geometry types, fields, coordinate systems, and output names.
Use try/except handling to catch and report errors.
Find and download census boundaries, a census/ACS numeric attribute, and roads (or another dataset with line geometry).
"""
import csv
import math
from pathlib import Path
import arcpy


def hawkid():
    return ["Elif Korkmaz", "ekorkmaz"]


# Problem 1 (20 points)
def prepare_data(input_fc, output_geodatabase, out_coordinate_system,
                 join_table=None, join_field=None, value_field=None):
    """Create or reuse the geodatabase; import and project one feature dataset.
    Use the input base name and return the prepared feature class path.
    For polygons, import a CSV's ID attribute and one numeric value
    and join that value using the join_field that . Supply all three join
    arguments together. Preserve inputs and reject existing output names.
    """
    input_fc = Path(input_fc)
    gdb = Path(output_geodatabase)

    try:
        # Step 1: The input must exist, be a feature class, and have a known CRS.
        if not arcpy.Exists(str(input_fc)):
            raise FileNotFoundError(f"Input does not exist: {input_fc}")
        desc = arcpy.Describe(str(input_fc))
        shape_type = getattr(desc, "shapeType", None)
        if shape_type not in ["Point", "Multipoint", "Polyline", "Polygon"]:
            raise TypeError(f"Input must be a point, line, or polygon feature class: {input_fc}")
        in_sr = desc.spatialReference
        if in_sr is None or in_sr.name == "Unknown":
            raise ValueError(f"Input has an unknown coordinate system: {input_fc}")

        # Step 2: The output CRS must be a projected EPSG code in meters.
        try:
            out_sr = arcpy.SpatialReference(int(out_coordinate_system))
        except (TypeError, ValueError, RuntimeError):
            raise ValueError(f"Invalid EPSG code: {out_coordinate_system}") from None
        if out_sr.type != "Projected" or out_sr.linearUnitName.lower() not in ["meter", "metre"]:
            raise ValueError(f"Output CRS '{out_sr.name}' must be projected in meters.")

        # Step 3: Join arguments are optional, but all three must be given together.
        join_args = [join_table, join_field, value_field]
        joining = all(arg is not None for arg in join_args)
        if any(arg is not None for arg in join_args) and not joining:
            raise ValueError("Supply join_table, join_field, and value_field together.")

        csv_values = {}
        if joining:
            join_table = Path(join_table)
            if shape_type != "Polygon":
                raise TypeError("A CSV attribute can only be joined to polygons.")
            if not join_table.is_file() or join_table.suffix.lower() != ".csv":
                raise FileNotFoundError(f"Join table must be an existing CSV file: {join_table}")

            # The key must be a text field in the input; the value field must be new.
            input_fields = [f.name for f in arcpy.ListFields(str(input_fc))]
            if join_field not in input_fields:
                raise KeyError(f"Field '{join_field}' not found in {input_fc}")
            if arcpy.ListFields(str(input_fc), join_field)[0].type != "String":
                raise TypeError(f"'{join_field}' must be a text field in {input_fc}")
            if value_field in input_fields:
                raise ValueError(f"{input_fc} already has a field named '{value_field}'.")

            # Read the CSV key and numeric value (text keys keep leading zeros).
            with open(join_table, encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                columns = reader.fieldnames or []
                if join_field not in columns or value_field not in columns:
                    raise KeyError(f"CSV must contain '{join_field}' and '{value_field}'. "
                                   f"Found: {columns}")
                for row in reader:
                    key = (row[join_field] or "").strip()
                    if key == "" or key in csv_values:
                        raise ValueError(f"CSV '{join_field}' values must be unique and "
                                         f"not empty (problem with '{key}').")
                    try:
                        value = float(row[value_field])
                    except (TypeError, ValueError):
                        raise ValueError(f"Non-numeric '{value_field}' for {key}: "
                                         f"{row[value_field]!r}") from None
                    if not math.isfinite(value):
                        raise ValueError(f"Invalid '{value_field}' for {key}.")
                    csv_values[key] = value
            if not csv_values:
                raise ValueError(f"No records found in {join_table}")

            # Every polygon ID must be unique and must have a CSV record.
            with arcpy.da.SearchCursor(str(input_fc), [join_field]) as rows:
                ids = [row[0] for row in rows]
            if len(ids) != len(set(ids)):
                raise ValueError(f"'{join_field}' values in {input_fc} must be unique.")
            missing = [i for i in ids if i not in csv_values]
            if missing:
                raise ValueError(f"{len(missing)} polygon IDs are not in the CSV, "
                                 f"e.g. {missing[:3]}")

        # Step 4: Create the geodatabase, or reuse it if it has the same CRS.
        if gdb.suffix.lower() != ".gdb":
            raise ValueError(f"Output geodatabase must end with .gdb: {gdb}")
        if arcpy.Exists(str(gdb)):
            with arcpy.EnvManager(workspace=str(gdb)):
                for name in arcpy.ListFeatureClasses() or []:
                    sr = arcpy.Describe(str(gdb / name)).spatialReference
                    if sr.name != out_sr.name:
                        raise ValueError(f"{gdb.name} already has '{name}' in {sr.name}. "
                                         "Use a new geodatabase for another CRS.")
        else:
            if not gdb.parent.is_dir():
                raise FileNotFoundError(f"Folder does not exist: {gdb.parent}")
            arcpy.management.CreateFileGDB(str(gdb.parent), gdb.name)

        # Step 5: Keep the input base name and reject names that already exist.
        base_name = desc.baseName
        if arcpy.ValidateTableName(base_name, str(gdb)) != base_name:
            raise ValueError(f"'{base_name}' is not a valid geodatabase name.")
        out_fc = gdb / base_name
        table = gdb / f"{base_name}_attributes"
        if arcpy.Exists(str(out_fc)):
            raise FileExistsError(f"'{base_name}' already exists in {gdb.name}.")
        if joining and arcpy.Exists(str(table)):
            raise FileExistsError(f"'{table.name}' already exists in {gdb.name}.")

        # Step 6: Import and project a copy (the input is not changed).
        if in_sr.name == out_sr.name:
            arcpy.management.CopyFeatures(str(input_fc), str(out_fc))
        else:
            transformations = arcpy.ListTransformations(in_sr, out_sr)
            transformation = transformations[0] if transformations else ""
            arcpy.management.Project(str(input_fc), str(out_fc), out_sr, transformation)

        # Step 7: Import the CSV key and value as a table and join the value.
        if joining:
            arcpy.management.CreateTable(str(gdb), table.name)
            key_length = max(len(key) for key in csv_values)
            arcpy.management.AddField(str(table), join_field, "TEXT", field_length=key_length)
            arcpy.management.AddField(str(table), value_field, "DOUBLE")
            with arcpy.da.InsertCursor(str(table), [join_field, value_field]) as rows:
                for key, value in csv_values.items():
                    rows.insertRow([key, value])
            arcpy.management.JoinField(str(out_fc), join_field, str(table),
                                       join_field, [value_field])

        print(f"Prepared {out_fc} in {out_sr.name}")
        return str(out_fc)

    except Exception as error:
        print(f"### Error in prepare_data: {error}")
        raise


# Problem 2 (40 points)
def estimatePopulationInZone(source_polygons, population_field, study_zone,
                             output_fc):
    """Similar to the week 10 and 11 notebook exercises, you overlay a buffer with source_polygons 
    such as census units, and calculate the proportion of a source polygon that overlaps 
    with the buffer (the study zone) using areal interpolation. 
    Combine the study zone, intersect, calculate area-weighted population,
    and total the estimates. Save SRC_KM2, PART_KM2, and EST_POP; return the total.
    Inputs must share a projected CRS in meters. 
    """
    source = str(Path(source_polygons))
    zone = str(Path(study_zone))
    output_fc = str(Path(output_fc))
    gdb = Path(output_fc).parent
    temp_source = r"memory\hw3_source_copy"
    temp_zone = r"memory\hw3_zone_dissolved"

    try:
        # Step 1: Both inputs must exist and be polygons.
        for fc in [source, zone]:
            if not arcpy.Exists(fc):
                raise FileNotFoundError(f"Input does not exist: {fc}")
            if getattr(arcpy.Describe(fc), "shapeType", None) != "Polygon":
                raise TypeError(f"Input must be a polygon feature class: {fc}")

        # Step 2: Both inputs must share one projected CRS in meters (no reprojection here).
        source_sr = arcpy.Describe(source).spatialReference
        zone_sr = arcpy.Describe(zone).spatialReference
        if source_sr.type != "Projected" or source_sr.linearUnitName.lower() not in ["meter", "metre"]:
            raise ValueError(f"Source polygons must use a projected CRS in meters, "
                             f"not '{source_sr.name}'. Run prepare_data() first.")
        if source_sr.name != zone_sr.name:
            raise ValueError(f"Source polygons ({source_sr.name}) and study zone "
                             f"({zone_sr.name}) must use the same CRS.")

        # Step 3: The population field must exist, be numeric, and hold nonnegative counts.
        fields = arcpy.ListFields(source, population_field)
        if not fields:
            raise KeyError(f"Field '{population_field}' not found in {source}")
        if fields[0].type not in ["SmallInteger", "Integer", "BigInteger", "Single", "Double"]:
            raise TypeError(f"'{population_field}' must be numeric, not {fields[0].type}.")
        with arcpy.da.SearchCursor(source, [population_field]) as rows:
            for (value,) in rows:
                if value is None or value < 0:
                    raise ValueError(f"'{population_field}' has a missing or negative value.")

        # Step 4: The new field names must not already be used in the source.
        existing = [f.name.upper() for f in arcpy.ListFields(source)]
        for name in ["SRC_KM2", "PART_KM2", "EST_POP"]:
            if name in existing:
                raise ValueError(f"Source polygons already have a field named {name}.")

        # Step 5: Output goes to an existing geodatabase under a new name.
        if gdb.suffix.lower() != ".gdb" or not arcpy.Exists(str(gdb)):
            raise FileNotFoundError(f"Output geodatabase does not exist: {gdb}")
        if arcpy.Exists(output_fc):
            raise FileExistsError(f"Output already exists: {output_fc}")

        # Step 6: Copy the source (to preserve the input) and save the full area.
        for temp in [temp_source, temp_zone]:
            if arcpy.Exists(temp):
                arcpy.management.Delete(temp)
        arcpy.management.CopyFeatures(source, temp_source)
        arcpy.management.AddField(temp_source, "SRC_KM2", "DOUBLE")
        arcpy.management.CalculateGeometryAttributes(
            temp_source, [["SRC_KM2", "AREA"]], area_unit="SQUARE_KILOMETERS")

        # Step 7: Dissolve the study zone so overlapping areas are counted once.
        arcpy.management.Dissolve(zone, temp_zone)

        # Step 8: Intersect to get the overlap pieces with the source attributes.
        arcpy.analysis.Intersect([temp_source, temp_zone], output_fc, "NO_FID")
        arcpy.management.AddField(output_fc, "PART_KM2", "DOUBLE")
        arcpy.management.AddField(output_fc, "EST_POP", "DOUBLE")

        # Step 9: No overlap, keep the empty output and return zero.
        if int(arcpy.management.GetCount(output_fc)[0]) == 0:
            print("No overlap between the source polygons and the study zone.")
            return 0.0

        # Step 10: Overlap area of each piece.
        arcpy.management.CalculateGeometryAttributes(
            output_fc, [["PART_KM2", "AREA"]], area_unit="SQUARE_KILOMETERS")

        # Step 11: Area-weighted population (assumes uniform population in each polygon).
        arcpy.management.CalculateField(
            output_fc, "EST_POP",
            f"!{population_field}! * !PART_KM2! / !SRC_KM2!", "PYTHON3")

        # Check that each area fraction is between 0 and 1.
        with arcpy.da.SearchCursor(output_fc, ["PART_KM2", "SRC_KM2"]) as rows:
            for part, full in rows:
                if not full or full <= 0 or not -1e-6 <= part / full <= 1 + 1e-6:
                    raise ValueError("Unexpected area fraction; inspect the geometry.")

        # Step 12: Total the estimates (unrounded).
        total = 0.0
        with arcpy.da.SearchCursor(output_fc, ["EST_POP"]) as rows:
            for (estimate,) in rows:
                total += estimate
        print(f"Estimated population in the study zone: {total:,.2f}")
        return total

    except Exception as error:
        print(f"### Error in estimatePopulationInZone: {error}")
        raise
    finally:
        for temp in [temp_source, temp_zone]:
            if arcpy.Exists(temp):
                arcpy.management.Delete(temp)


# Problem 3 (40 points)
def summarizeLineLength(lines, polygons, polygon_id_field, output_fc):
    """Compute the total length of lines that intersect a polygon. 
    Intersect, measure lengths, summarize by polygon ID, and join totals back.
    Save all polygons with LINE_KM (zero if no lines); return output_fc.
    Use a shared projected CRS in meters.
    """
    lines = str(Path(lines))
    polygons = str(Path(polygons))
    output_fc = str(Path(output_fc))
    gdb = Path(output_fc).parent
    temp_pieces = r"memory\hw3_line_pieces"
    temp_stats = r"memory\hw3_line_stats"

    try:
        # Step 1: Inputs must exist and have the right geometry types.
        for fc, shape in [(lines, "Polyline"), (polygons, "Polygon")]:
            if not arcpy.Exists(fc):
                raise FileNotFoundError(f"Input does not exist: {fc}")
            if getattr(arcpy.Describe(fc), "shapeType", None) != shape:
                raise TypeError(f"Input must be a {shape} feature class: {fc}")

        # Step 2: Both inputs must share one projected CRS in meters (no reprojection here).
        line_sr = arcpy.Describe(lines).spatialReference
        poly_sr = arcpy.Describe(polygons).spatialReference
        if poly_sr.type != "Projected" or poly_sr.linearUnitName.lower() not in ["meter", "metre"]:
            raise ValueError(f"Polygons must use a projected CRS in meters, "
                             f"not '{poly_sr.name}'. Run prepare_data() first.")
        if line_sr.name != poly_sr.name:
            raise ValueError(f"Lines ({line_sr.name}) and polygons ({poly_sr.name}) "
                             "must use the same CRS.")

        # Step 3: The polygon ID must be a text or integer field with unique values.
        fields = arcpy.ListFields(polygons, polygon_id_field)
        if not fields:
            raise KeyError(f"Field '{polygon_id_field}' not found in {polygons}")
        if fields[0].type not in ["String", "SmallInteger", "Integer", "BigInteger"]:
            raise TypeError(f"'{polygon_id_field}' must be a text or integer field.")
        with arcpy.da.SearchCursor(polygons, [polygon_id_field]) as rows:
            ids = [row[0] for row in rows]
        if None in ids or "" in ids or len(ids) != len(set(ids)):
            raise ValueError(f"'{polygon_id_field}' values must be unique and not empty.")

        # Step 4: LINE_KM must not already exist in the polygons.
        if "LINE_KM" in [f.name.upper() for f in arcpy.ListFields(polygons)]:
            raise ValueError("Polygons already have a field named LINE_KM.")

        # Step 5: Output goes to an existing geodatabase under a new name.
        if gdb.suffix.lower() != ".gdb" or not arcpy.Exists(str(gdb)):
            raise FileNotFoundError(f"Output geodatabase does not exist: {gdb}")
        if arcpy.Exists(output_fc):
            raise FileExistsError(f"Output already exists: {output_fc}")

        # Step 6: Intersect lines with polygons. Polygons go first so the ID keeps
        # its name. output_type="LINE" keeps shared-boundary lines in both polygons
        # and drops point-only touches.
        for temp in [temp_pieces, temp_stats]:
            if arcpy.Exists(temp):
                arcpy.management.Delete(temp)
        arcpy.analysis.Intersect([polygons, lines], temp_pieces, "ALL",
                                 output_type="LINE")

        if int(arcpy.management.GetCount(temp_pieces)[0]) == 0:
            arcpy.management.CopyFeatures(polygons, output_fc)
            arcpy.management.AddField(output_fc, "LINE_KM", "DOUBLE")
            arcpy.management.CalculateField(output_fc, "LINE_KM", "0", "PYTHON3")
            print("No lines intersect the polygons; LINE_KM is 0 for all polygons.")
            return output_fc

        # Step 7: Measure each line piece in kilometers.
        arcpy.management.AddField(temp_pieces, "PIECE_KM", "DOUBLE")
        arcpy.management.CalculateGeometryAttributes(
            temp_pieces, [["PIECE_KM", "LENGTH"]], length_unit="KILOMETERS")

        # Step 8: Sum the lengths for each polygon ID (creates SUM_PIECE_KM).
        arcpy.analysis.Statistics(temp_pieces, temp_stats,
                                  [["PIECE_KM", "SUM"]], polygon_id_field)

        # Step 9: Copy all polygons and join the totals back.
        arcpy.management.CopyFeatures(polygons, output_fc)
        arcpy.management.JoinField(output_fc, polygon_id_field, temp_stats,
                                   polygon_id_field, ["SUM_PIECE_KM"])

        # Step 10: Save LINE_KM, using zero for polygons with no lines.
        arcpy.management.AddField(output_fc, "LINE_KM", "DOUBLE")
        arcpy.management.CalculateField(
            output_fc, "LINE_KM",
            "0 if !SUM_PIECE_KM! is None else !SUM_PIECE_KM!", "PYTHON3")
        arcpy.management.DeleteField(output_fc, ["SUM_PIECE_KM"])

        print(f"Saved line lengths for {len(ids)} polygons: {output_fc}")
        return output_fc

    except Exception as error:
        print(f"### Error in summarizeLineLength: {error}")
        raise
    finally:
        for temp in [temp_pieces, temp_stats]:
            if arcpy.Exists(temp):
                arcpy.management.Delete(temp)


######################################################################
# MAKE NO CHANGES BEYOND THIS POINT.
######################################################################
if __name__ == "__main__" and hawkid()[1] == "hawkid":
    print("### Error: YOU MUST provide your HawkID in the hawkid() function.")
