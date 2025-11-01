# IPA-Project
06016423 Infrastructure Programmability and Automation 2025 Project

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt

<!-- Installing tailwind -->
npm install

<!-- To start project -->
<!-- These docker container and volume names can be changed due to your satisfactory ! -->
docker pull mongo
docker volume create mongo-data
docker run -d -p 27017:27017 --name my-mongo-db -v mongo-data:/data/db mongo
Run Flask + Tailwind together ==> npm run dev