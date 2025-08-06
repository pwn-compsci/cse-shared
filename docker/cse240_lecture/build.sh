echo "Starting...." |tee -a /tmp/push.log;
cd /cse/intro-to-programming-languages/_web_dev; 
cp wsgi.py /cse/cse-shared/docker/cse240_lecture/wsgi.py; 
cp lecture.html /cse/cse-shared/docker/cse240_lecture/templates/lecture.html; 
cd /cse/cse-shared/docker/cse240_lecture; 

cp ../../common/redirector.py /cse/cse-shared/docker/cse240_lecture/redirector.py;

docker build -t tricke/cse240-lecture . | tee -a /tmp/push.log 2>&1

if [ $? -ne 0 ]; then
  echo "Docker build failed, exiting." | tee -a /tmp/push.log
  exit 1
fi

docker push -q tricke/cse240-lecture | tee -a /tmp/push.log 2>&1
if [ $? -ne 0 ]; then
  echo "Docker push failed, exiting." | tee -a /tmp/push.log
  exit 1
fi
echo "Finished: $(date)" | tee -a /tmp/push.log

