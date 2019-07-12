# DLambda
Django + Textract + AWS Lambda API integration

Input

```
{
    "name": "JADE 975772528 INVOICE.pdf",
    "inputFormat": {
        "input_first": [
            [
                "invoice number",
                "Invoice #",
                "Invoice num"
            ],
            [
                "date shippped",
                "date #",
                "Invoice date"
            ]
        ],
        "input_second": [
            [
                "pieces",
                "Quantity",
                "Qty"
            ],
            [
                "description",
                "Desc",
                "Description #"
            ],
            [
                "rate"
            ],
            [
                "price"
            ]
        ]
    }
}
```
