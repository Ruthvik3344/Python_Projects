print('Available Files are:')
print('Sample.txt')
try:
    file=(input("Enter file name: "))
    sample_file=open(file,'r')
    read=sample_file.readline()
    read1=sample_file.readline()
    print('Reading File Content:')
    print('Line 1:',read)
    print('Line 2:',read1)
    sample_file.close()
except FileNotFoundError:
    print('Error: The file ',file,' was not found.')
finally:
    print("Thank You! for reading the file.")

