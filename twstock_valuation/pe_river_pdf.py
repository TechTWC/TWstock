f"Latest close    {number(metadata.get('latest_adjusted_close', metadata['latest_close']))} TWD",

        f"First valid PE  {metadata.get('first_valid_pe_date') or 'Unavailable'}",
