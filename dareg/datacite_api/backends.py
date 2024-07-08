from api.models import Dataset
import datetime, os
# from decouple import config

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

def build_datacite_request(dataset: Dataset):
    return {
                "data": {
                    "type": "dois",
                    "attributes": {
                        "prefix": "10.82592",
                        "event": "publish" if dataset.doi else None,
                        "creators": [
                            {
                                "name": dataset.created_by.get_full_name()
                            }
                        ],
                        "titles": [
                            {
                                "title": dataset.name
                            }
                        ],
                        "publisher": dataset.project.facility.name,
                        "publicationYear": str(datetime.date.today()),
                        "types": {
                            "resourceTypeGeneral": "Text"
                        },
                        "url": f"{FRONTEND_URL}/collections/{dataset.project.id}/datasets/{dataset.id}"
                    }
                }
            }
