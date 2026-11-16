###################################################################### 
# Edit the following function definition, replacing the words
# 'name' with your name and 'hawkid' with your hawkid.
# 
# Note: Your hawkid is the login name you use to access ICON, and not
# your firsname-lastname@uiowa.edu email address.
# 
# def hawkid():
#     return(["Caglar Koylu", "ckoylu"])
###################################################################### 
def hawkid():
    return(["Elif Korkmaz", "ekorkmaz"])

###################################################################### 
# Problem 1 (10 Points)
#
# This function reads all the feature classes in a workspace (folder or geodatabase) and
# prints the name of each feature class and the geometry type of that feature class in the following format:
# 'states is a point feature class'

###################################################################### 
import os
import arcpy

def printFeatureClassNames(workspace):
    try:
        if not arcpy.Exists(workspace):  # check that the workspace exists
            print("Workspace does not exist:", workspace)
            return
        
        arcpy.env.workspace = workspace 
        featureClasses = arcpy.ListFeatureClasses()
        if not featureClasses:
            print("No feature classes found in", workspace)
            return

        for fc in featureClasses:
            desc = arcpy.Describe(fc)
            geometry = desc.shapeType.lower()
            if geometry == "polyline":
                geometry = "line"
            print(f"{desc.baseName} is a {geometry} feature class") # baseName = name without extension (.shp)

    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))  # Geoprocessing tool errors
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}")

###################################################################### 
# Problem 2 (20 Points)
#
# This function reads all the attribute names in a feature class or shape file and
# prints the name of each attribute name and its type (e.g., integer, float, double)
# only if it is a numerical type

###################################################################### 
def printNumericalFieldNames(inputFc, workspace):
    try:
        arcpy.env.workspace = workspace # so ArcPy can find inputFc by its name
        if not arcpy.Exists(inputFc): # check that the feature class exists
            print("Feature class does not exist:", inputFc)
            return

        # Print only fields with a numerical type
        numericTypes = ["SmallInteger", "Integer", "BigInteger", "Single", "Double"]
        for field in arcpy.ListFields(inputFc): # reads all the attribute names (fields)
            if field.type in numericTypes:
                print(field.name, field.type)

    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}")

###################################################################### 
# Problem 3 (30 Points)
#
# Given a geodatabase with feature classes, and shape type (point, line or polygon) and an output geodatabase:
# this function creates a new geodatabase and copying only the feature classes with the given shape type into the new geodatabase

###################################################################### 
def exportFeatureClassesByShapeType(input_geodatabase, shapeType, output_geodatabase):
    try:
        if not arcpy.Exists(input_geodatabase):
            print("Input geodatabase does not exist:", input_geodatabase)
            return

        # Convert user input to ArcPy shape types (ArcPy calls lines "Polyline")
        types = {"point": "Point", "line": "Polyline", "polygon": "Polygon"}
        
        if shapeType.lower() not in types:
            print("Shape type must be point, line, or polygon")
            return

        # Make sure the output name ends with .gdb
        if not output_geodatabase.lower().endswith(".gdb"):
            output_geodatabase = output_geodatabase + ".gdb"

        # Do not overwrite an existing geodatabase
        if arcpy.Exists(output_geodatabase):
            print("Output geodatabase already exists:", output_geodatabase)
            return

        # Create the new geodatabase
        folder = os.path.dirname(output_geodatabase)
        name = os.path.basename(output_geodatabase)
        arcpy.management.CreateFileGDB(folder, name)
        

        # List only the feature classes with the given shape type and copy them
        arcpy.env.workspace = input_geodatabase
        
        for fc in arcpy.ListFeatureClasses(feature_type=types[shapeType.lower()]):
            arcpy.management.CopyFeatures(fc, os.path.join(output_geodatabase, fc))
        

    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}")

###################################################################### 
# Problem 4 (40 Points)
#
# Given an input feature class or a shape file and a table in a geodatabase or a folder workspace,
# join the table to the feature class using one-to-one and export to a new feature class.
# Print the results of the joined output to show how many records matched and unmatched in the join operation. 

###################################################################### 
def exportAttributeJoin(inputFc, idFieldInputFc, inputTable, idFieldTable, workspace):
    
    layer = "join_layer"

    try:
        # Set the workspace and check that the inputs exist
        arcpy.env.workspace = workspace
        if not arcpy.Exists(inputFc) or not arcpy.Exists(inputTable):
            print("Input feature class or table does not exist")
            return
 
        # Check that both ID fields exist
        if idFieldInputFc not in [f.name for f in arcpy.ListFields(inputFc)]:
            print("Field does not exist:", idFieldInputFc)
            return
        if idFieldTable not in [f.name for f in arcpy.ListFields(inputTable)]:
            print("Field does not exist:", idFieldTable)
            return
 
        # A join is added to a layer, so make a temporary feature layer first
        if arcpy.Exists(layer):
            arcpy.management.Delete(layer)
        arcpy.management.MakeFeatureLayer(inputFc, layer)
 
        # KEEP_ALL keeps unmatched features; JOIN_ONE_TO_FIRST makes the join one-to-one
        arcpy.management.AddJoin(layer, idFieldInputFc, inputTable, idFieldTable,
                                 "KEEP_ALL", join_operation="JOIN_ONE_TO_FIRST")
 
        # After the join, the table's ID field is named "<table>.<field>"
        fcName = arcpy.Describe(inputFc).baseName
        joinedField = None
        for field in arcpy.ListFields(layer):
            name = field.name.lower()
            if name.endswith("." + idFieldTable.lower()) and not name.startswith(fcName.lower() + "."):
                joinedField = field.name
 
        # Count matches: unmatched features have a null value in the joined ID field
        matched = 0
        unmatched = 0
        with arcpy.da.SearchCursor(layer, [joinedField]) as rows:
            for (value,) in rows:
                if value is None:
                    unmatched += 1
                else:
                    matched += 1
 
        # Export to a new feature class (a shapefile if the workspace is a folder);
        # CreateUniqueName avoids overwriting an existing output
        outName = fcName + "_join"
        if arcpy.Describe(workspace).workspaceType == "FileSystem":
            outName = outName + ".shp"
        outFc = arcpy.CreateUniqueName(outName, workspace)
        arcpy.management.CopyFeatures(layer, outFc)
 
        # Check the output and print the join results
        count = int(arcpy.management.GetCount(outFc)[0])
        print("Output features:", count)
        print("Matched records:", matched)
        print("Unmatched records:", unmatched)
 
    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}")
 
######################################################################
# MAKE NO CHANGES BEYOND THIS POINT.
######################################################################
if __name__ == '__main__' and hawkid()[1] == "hawkid":
    print('### Error: YOU MUST provide your hawkid in the hawkid() function.')
