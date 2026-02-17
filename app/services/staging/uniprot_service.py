import requests

class UniprotServiceError(Exception):
    pass

class UniprotService:
    BASE_URL = "https://rest.uniprot.org/uniprotkb/"

    @staticmethod
    def fetch(accession: str) -> dict:
        '''
        Returns:
         {
            "sequence": "MKK...",
            "protein_length": 123,
            "features": [ { "type": "...", "description": "...", "start": 1, "end": 50 }, ... ]
          }
        '''
        accession = accession.strip().upper()
        if not accession:
            raise UniprotServiceError("Empty accession")
        
        url = f'{UniprotService.BASE_URL}{accession}.json'
        r = requests.get(url, timeout=15, headers={"Accept": "application/json"})

        if r.status_code == 404:
            raise UniprotServiceError(f"Accession {accession} not found in UniProt")
        if r.status_code == 400:
            raise UniprotServiceError(f"Invalid accession format: {accession}. Please check the accession ID.")
        if not r.ok:
            raise UniprotServiceError(f"UniProt request failed with status {r.status_code}")
        
        data = r.json()

        #sequence
        seq_obj = data.get("sequence") or {}
        seq = seq_obj.get("value")
        if not seq:
            raise UniprotServiceError(f"No sequence found for accession {accession}")
        
        #features (domain, site, region, etc)
        features_out = []
        for f in data.get("features", []) or []:
            loc = f.get("location", {})
            start = (loc.get("start") or {}).get("value")
            end = (loc.get("end") or {}).get("value")

            features_out.append({
                "type": f.get("type"),
                "description": f.get("description") or f.get("featureId") or "",
                "start": start,
                "end": end
            })

        return {
            "sequence": seq,
            "protein_length": len(seq),
            "features": features_out,
            "protein_name": (data.get("proteinDescription", {})
                             .get("recommendedName", {})
                             .get("fullName", {})
                             .get("value"))
                            or (data.get("proteinDescription", {})
                                .get("submissionNames", [{}])[0]
                                .get("fullName", {})
                                .get("value")),
            "organism": (data.get("organism", {})
                         .get("scientificName")),
        }
