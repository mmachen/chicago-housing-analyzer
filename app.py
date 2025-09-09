from flask import Flask, render_template, jsonify, request
import pandas as pd
import numpy as np
import socket

app = Flask(__name__)

# Load data
try:
    df = pd.read_csv('output/final_data.csv')
    print(f"Successfully loaded {len(df)} properties from output/final_data.csv")
except Exception as e:
    print(f"Error loading output/final_data.csv: {str(e)}")
    df = pd.DataFrame()  # Empty DataFrame as fallback

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/initial-data')
def get_initial_data():
    try:
        locations = sorted(df['LOCATION'].dropna().unique().astype(str).tolist()) if not df.empty and 'LOCATION' in df.columns else []
    except Exception:
        locations = []
    
    price_ranges = [
        (0, 300000), (300000, 400000), (400000, 500000), (500000, 600000),
        (600000, 700000), (700000, 800000), (800000, 900000), (900000, 1000000),
        (1000000, 1000001)  # $1M+
    ]
    
    return jsonify({
        'locations': locations,
        'price_ranges': price_ranges
    })

@app.route('/api/properties')
def get_properties():
    try:
        # Get filter parameters
        location = request.args.get('location', '')
        price_min = request.args.get('price_min', type=float)
        price_max = request.args.get('price_max', type=float)
        sort_by = request.args.get('sort_by', 'PRICE')
        sort_order = request.args.get('sort_order', 'asc')

        # Start with all properties
        filtered_df = df

        # Apply filters
        if location and location in filtered_df['LOCATION'].unique():
            filtered_df = filtered_df[filtered_df['LOCATION'] == location]
        
        if price_min is not None:
            filtered_df = filtered_df[filtered_df['PRICE'] >= price_min]
        
        if price_max is not None:
            if price_max == 1000001:  # Special case for $1M+
                filtered_df = filtered_df[filtered_df['PRICE'] >= 1000000]
            else:
                filtered_df = filtered_df[filtered_df['PRICE'] <= price_max]

        # Sort (safely). Allow sorting by OVERALL_SCORE, compute if present.
        if sort_by not in filtered_df.columns:
            sort_by = 'PRICE'
        ascending = (str(sort_order).lower() != 'desc')
        try:
            filtered_df = filtered_df.sort_values(by=sort_by, ascending=ascending)
        except Exception:
            # Fallback to PRICE if sort fails due to dtype issues
            if 'PRICE' in filtered_df.columns:
                filtered_df = filtered_df.sort_values(by='PRICE', ascending=ascending)

        # Convert to list of dictionaries
        properties = filtered_df.to_dict('records')
        
        # Convert numpy types to Python native types
        for prop in properties:
            for key, value in prop.items():
                if isinstance(value, (np.integer, np.floating)):
                    prop[key] = value.item()
                elif isinstance(value, np.ndarray):
                    prop[key] = value.tolist()
                elif pd.isna(value):
                    prop[key] = None

        return jsonify(properties)
    except Exception as e:
        print(f"Error in get_properties: {str(e)}")
        return jsonify([])

if __name__ == '__main__':
    # Get local IP address
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"\nLocal IP address: {local_ip}")
    print("Access the application at:")
    print(f"  Local:   http://localhost:5000")
    print(f"  Network: http://{local_ip}:5000\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True) 