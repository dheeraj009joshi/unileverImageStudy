# Study Export Functionality

## Overview
The study export functionality allows researchers to download comprehensive CSV files containing all completed study responses in a structured, analysis-ready format.

## Export Features

### 📊 **Comprehensive Data Export**
The CSV export includes all the data from your study responses, formatted in a grid-like structure similar to the example you provided:

#### **1. Response-Level Information**
- Response ID, Session ID, Respondent ID, Study ID
- Session start/end times and total duration
- Completion status and percentage
- Task completion counts

#### **2. Classification Questions**
- All demographic and screening responses
- Question IDs and text for easy identification
- Answer values in separate columns

#### **3. Personal Information**
- Birth date, age, and gender
- Any additional personal data collected

#### **4. Task-by-Task Data**
- Individual task information for each completed task
- Task timing (start, completion, duration)
- Ratings given and timestamps
- Element exposure data

#### **5. Element Information**
- Which elements were shown in each task
- Element content URLs
- Element visibility status (shown/hidden)

## CSV Structure

### **Header Row Example**
```
Response ID, Session ID, Respondent ID, Study ID, Session Start Time, Session End Time, Total Duration (seconds), Completion Status, Tasks Completed, Total Tasks Assigned, Completion Percentage, Is Abandoned, Classification_Q1_do you like this deo, Classification_Q2_Do you use antiperspirants, Personal_Birth_Date, Personal_Age, Personal_Gender, Task_1_Task_ID, Task_1_Task_Index, Task_1_Start_Time, Task_1_Completion_Time, Task_1_Duration_Seconds, Task_1_Rating_Given, Task_1_Rating_Timestamp, Task_1_E1_Shown, Task_1_E1_Content, Task_1_E2_Shown, Task_1_E2_Content, Task_1_E3_Shown, Task_1_E3_Content, Task_1_E4_Shown, Task_1_E4_Content, Task_2_Task_ID, Task_2_Task_Index, Task_2_Start_Time, Task_2_Completion_Time, Task_2_Duration_Seconds, Task_2_Rating_Given, Task_2_Rating_Timestamp, Task_2_E1_Shown, Task_2_E1_Content, Task_2_E2_Shown, Task_2_E2_Content, Task_2_E3_Shown, Task_2_E3_Content, Task_2_E4_Shown, Task_2_E4_Content, ...
```

### **Data Row Example**
```
0fd6479b-9a28-4288-9475-ffef4a31bec6, d49bdd23-b0fb-49bb-9843-bce271b133f4, 8, 7223cd83-dfa8-47e7-932d-d19ea630bd8b, 2025-01-20T10:45:02.885000, 2025-01-20T11:45:32.924000, 3222.046, Completed, 24, 24, 100.0, false, yes, yes, 2003-08-21, 22, male, task_1, 0, 2025-01-20T10:48:04.124000, 2025-01-20T10:48:26.991000, 122.867, 4, 2025-01-20T10:48:26.991000, 1, https://printxd.blob.core.windows.net/mf2/04a0835b-5f9e-48a8-bfd9-cf9bbfdd7440.png, 1, https://printxd.blob.core.windows.net/mf2/ff40b595-21e2-4b99-aeac-48f6a2cdd2d2.png, 0, https://printxd.blob.core.windows.net/mf2/83b5da64-d149-4a71-8e26-f37f986b6f13.png, 1, https://printxd.blob.core.windows.net/mf2/0fba094a-d9df-4495-b1f5-635d2b0a56ea.png, task_2, 1, 2025-01-20T10:48:33.159000, 2025-01-20T10:48:35.046000, 1.887, 6, 2025-01-20T10:48:35.046000, 1, https://printxd.blob.core.windows.net/mf2/04a0835b-5f9e-48a8-bfd9-cf9bbfdd7440.png, 0, https://printxd.blob.core.windows.net/mf2/ff40b595-21e2-4b99-aeac-48f6a2cdd2d2.png, 1, https://printxd.blob.core.windows.net/mf2/83b5da64-d149-4a71-8e26-f37f986b6f13.png, 1, https://printxd.blob.core.windows.net/mf2/0fba094a-d9df-4495-b1f5-635d2b0a56ea.png, ...
```

## How to Use

### **1. Access Export Function**
1. Go to your study dashboard
2. Click on "Study Responses" for the study you want to export
3. Click the "📊 Export Study Results (CSV)" button

### **2. Automatic Download**
- File will be automatically downloaded
- Filename format: `StudyName_YYYY-MM-DD.csv`
- Example: `Deodorant_Study_2025-01-20.csv`

### **3. Data Analysis**
- Open in Excel, Google Sheets, or any CSV-compatible software
- Use for statistical analysis, data visualization, or reporting
- Perfect for academic research and business intelligence

## Data Structure Details

### **Grid Studies**
For grid studies, each task includes:
- Task metadata (ID, index, timing, rating)
- Element visibility (shown/hidden for each element)
- Element content URLs

### **Layer Studies**
For layer studies, each task includes:
- Task metadata (ID, index, timing, rating)
- Layer configuration (z-index, order)
- Layer-specific information

### **Classification Questions**
- Dynamic columns based on your study's classification questions
- Question text included in column headers for clarity
- Answer values in corresponding cells

### **Personal Information**
- Standard demographic data
- Customizable based on your study requirements

## Benefits

### **1. Complete Data Export**
- All response data in one file
- No data loss or truncation
- Ready for immediate analysis

### **2. Structured Format**
- Consistent column structure
- Easy to import into analysis tools
- Clear data relationships

### **3. Research Ready**
- Academic research compliance
- Statistical analysis ready
- Publication quality data

### **4. Business Intelligence**
- Performance metrics
- User behavior analysis
- A/B testing results

## Technical Details

### **File Format**
- **Format**: CSV (Comma-Separated Values)
- **Encoding**: UTF-8
- **Delimiter**: Comma
- **Quote Character**: Double quotes

### **Data Types**
- **Text**: IDs, URLs, text responses
- **Numbers**: Ratings, durations, counts
- **Dates**: ISO 8601 format timestamps
- **Booleans**: Shown/hidden status

### **Performance**
- Optimized for large datasets
- Handles thousands of responses efficiently
- Memory-efficient processing

## Use Cases

### **Academic Research**
- Statistical analysis in R, Python, SPSS
- Publication data sharing
- Research collaboration

### **Business Analysis**
- User experience optimization
- Product performance metrics
- Market research insights

### **Quality Assurance**
- Data validation
- Response quality assessment
- Study effectiveness evaluation

## Future Enhancements

- **Multiple Export Formats**: Excel (.xlsx), JSON, XML
- **Filtered Exports**: Date ranges, response status
- **Real-time Exports**: Live data streaming
- **Automated Scheduling**: Regular export generation
- **API Access**: Programmatic data access

## Support

If you encounter any issues with the export functionality:
1. Check that you have completed responses in your study
2. Ensure you have proper permissions for the study
3. Contact support with specific error messages

---

*This export functionality provides researchers with comprehensive, analysis-ready data from their studies, enabling deeper insights and better decision-making.*
