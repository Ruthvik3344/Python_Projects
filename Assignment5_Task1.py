dict={'Alice':85,'Arjun':99,'David':75,'Neha':88}
name=str(input("Enter the student's name : "))
if name in dict:
    print(name,"'s marks:",dict[name])
else:
    print("Student not found.")

