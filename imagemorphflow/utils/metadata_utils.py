# import easygui as eg
import os
import csv

def plate_wells(plate_type=96, zero_pad=False):
    """ 
    Provide a plate type and return the well names.
    
    Args:
        plate_type (int): plate type accepted (6, 12, 24, 96, 384)
        zero_pad (bool): if True, pad column numbers with zero (e.g., A01)
    """
    import string
    import itertools

    # Define rows and columns per plate type
    if plate_type == 6:
        number_cols, number_rows = 3, 2
    elif plate_type == 12:
        number_cols, number_rows = 4, 3
    elif plate_type == 24:
        number_cols, number_rows = 6, 4
    elif plate_type == 96:
        number_cols, number_rows = 12, 8
    elif plate_type == 384:
        number_cols, number_rows = 24, 16
    else:
        raise ValueError("Unsupported plate type. Use 6, 12, 24, 96, or 384.")

    # Determine padding width (e.g., 01 for up to 9, 001 for up to 99)
    pad_width = len(str(number_cols)) if not zero_pad else 2

    # Generate row and column labels
    rows = list(string.ascii_uppercase[:number_rows])
    if zero_pad:
        columns = [str(num).zfill(pad_width) for num in range(1, number_cols + 1)]
    else:
        columns = [str(num) for num in range(1, number_cols + 1)]

    # Combine row and column labels
    wells = [''.join(pair) for pair in itertools.product(rows, columns)]

    print(f"Number of wells: {len(wells)}")
    print(wells)
    return wells

def get_samples(layout, plate_type=96):
    """ 
    """
    if plate_type == 24:
        number_cols = 6   # The ending number in the range (inclusive)
        number_rows = 4
    elif plate_type == 96:
        number_cols = 12   # The ending number in the range (inclusive)
        number_rows = 8
    elif plate_type == 12:
        number_cols = 4   # The ending number in the range (inclusive)
        number_rows = 3
    elif plate_type == 6:
        number_cols = 3   # The ending number in the range (inclusive)
        number_rows = 2
    elif plate_type == 384:
        number_cols = 24   # The ending number in the range (inclusive)
        number_rows = 16
    names = []
    for row in layout.iter_rows(max_row=number_rows,max_col=number_cols): #iterate through rows until 8 and cols till 12 (size of the 96 well plate)
        for cell in row: #iterate within the columns in each row
            names.append(str(cell.internal_value)) #append the cell values to the names list
    names_return = [t.rstrip() for t in names] #remove any spaces at the beggining or end of the string
    print(names_return)
    return names_return

def generate_rows_lists(samples, wells):
    """
    """

    sublist = []
    for s in range(len(samples)):
        if s != 'None':
            itens = samples[s].split()
            itens.insert(0, wells[s])
            sublist.append(itens)
        else:
            sublist.append([])
    return sublist

def get_example_to_name_metadata_cols(samples):
    example = next((s for s in samples if s != 'None'), None)  # Get the first non-'None' sample
    if example is None:
        print("No valid example found.")
        return []

    x = example.split(" ")  # Split the example into column names
    metadata_cols = []

    print("Write the name of the column for each example:")

    for col in x:
        value = input(f"Enter name for '{col}': ")
        metadata_cols.append(value)

    metadata_cols.insert(0, "well_position")  # Add 'well_position' at the beginning

    print(f"Column names: {metadata_cols}")

    return metadata_cols

def generate_csv(file_name, metadata_cols, sublist_add_platemap):

    os.makedirs("platemap", exist_ok=True)

    with open(rf"platemap\{file_name}.csv",'w',newline = '') as csvfile: #create a metadata.csv file 
        writer = csv.writer(csvfile, delimiter=',') #comma delimited
    #gives the header name row into csv
        writer.writerow([g for g in metadata_cols])
        for sub in sublist_add_platemap:
            if len(sub) == len(metadata_cols):
                writer.writerow(sub)

    #also generate a txt file
    with open(rf"platemap\{file_name}.csv", 'r') as f_in, open(f"platemap\{file_name}.txt", 'w') as f_out:
        # 2. Read the CSV file and store in variable
        content = f_in.read()
        # 3. Write the content into the TXT file
        f_out.write(content)