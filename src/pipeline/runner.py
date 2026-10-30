from src.ingestion.dataset_loader import DatasetLoader


loader = DatasetLoader("data")

folders = loader.get_meeting_folders()

print(f"Found {len(folders)} folders")

for folder in folders[:5]:
    print(folder.name)


meeting_0 = loader.load_raw_meeting(
    folders[0]
)

print(meeting_0.keys())

print(meeting_0)

meetings = loader.load_dataset()

print(
    f"Loaded {len(meetings)} meetings"
)

print(meetings[0].title)


from src.analytics.feature_extractor import (
    MeetingFeatureExtractor
)

extractor = MeetingFeatureExtractor()

features = extractor.extract(
    meetings[0]
)

print(features)